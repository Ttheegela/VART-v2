"""The CSF 2.0 gap check over HTTP (CSF spec 5.1, 7). Owner: lane 6B-api (Tasks 3-4)."""

import uuid
from typing import cast

from fastapi import APIRouter, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import csf
from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import limit
from app.api.runs import run_out, summary
from app.api.schemas import ERRORS, GapOut, GapRow, GapScope, RunOut
from app.contracts import ItemLabel, Value
from app.db.models import Answer, Item, Questionnaire, Run
from app.export import GapSheet
from app.runs import FAILED_TEXT, create_run
from app.services.capacity import ensure_capacity
from app.settings import get_settings

router = APIRouter(tags=["gap"], responses=ERRORS)
FAILED_SENTENCE = "Not checked: the model call failed twice. Press r to check again."  # adversary-1 M4


def latest_run(session: Session, questionnaire_id: uuid.UUID) -> Run | None:
    return session.scalar(
        select(Run)
        .where(Run.questionnaire_id == questionnaire_id)
        .order_by(Run.started_at.desc(), Run.id)
        .limit(1)
    )


def gap_rows(session: Session, scope: str, q: Questionnaire | None, run: Run | None) -> list[GapRow]:
    """Every outcome of the scope's functions in NIST's order, with the run's answer where it has one. The
    label is code's (`csf.gap_label`): none for a not-checked outcome, none before an outcome is answered,
    none for one marked not applicable (`not_applicable`, the visitor's reason as the explanation) or whose
    model call failed twice (the failure sentence)."""
    items = (
        {}
        if q is None
        else {i.csf_id: i for i in session.scalars(select(Item).where(Item.questionnaire_id == q.id))}
    )
    answers = (
        {}
        if run is None
        else {a.item_id: a for a in session.scalars(select(Answer).where(Answer.run_id == run.id))}
    )
    rows = []
    for o in csf.framework().outcomes:
        if scope != "core" and o.function.lower() != scope:
            continue
        item = items.get(o.id)
        a = answers.get(item.id) if item is not None else None
        na = a is not None and a.label == "na"
        failed = a is not None and o.tier == "checked" and a.text == FAILED_TEXT
        label = (
            csf.gap_label(o, cast(ItemLabel, a.label), cast(Value | None, a.value), a.statement_id)
            if a and not na and not failed
            else None
        )
        rows.append(
            GapRow(
                csf_id=o.id,
                function=o.function,
                category=o.category,
                outcome=o.outcome,
                related_controls=list(o.related_controls),
                source_url=o.source_url,
                tier=o.tier,
                item_id=item.id if item is not None else None,
                answer_id=a.id if a else None,
                label=label,
                explanation=FAILED_SENTENCE if failed else (a.text or None) if a and (label or na) else None,
                sources=summary(a).sources if a and label else 0,
                not_applicable=na,
            )
        )
    return rows


def gap_sheet(session: Session, q: Questionnaire, run: Run) -> GapSheet:
    """One gap-check run as a sheet (CSF spec 7): its rows, each answer's citations, its date, scope and the
    CSF data version it ran on (stored in the questionnaire's mapping)."""
    scope = q.mapping["scope"]
    cited = {a.id: a.citations for a in session.scalars(select(Answer).where(Answer.run_id == run.id))}
    return GapSheet(
        gap_rows(session, scope, q, run),
        cited,
        (run.finished_at or run.started_at).date().isoformat(),  # a Check again later dates the sheet then
        scope,
        q.mapping["csf_version"],
        csf.CONTROLS_URL,
    )


def latest_gap(session: Session, ws_id: uuid.UUID) -> tuple[Questionnaire, Run] | None:
    """The workspace's latest *finished* gap-check run, any scope (plan 6B decision 5); None when there is
    none. A run being checked again is running, so its older sheet is not offered until it is done."""
    found = session.execute(
        select(Questionnaire, Run)
        .join(Run, Run.questionnaire_id == Questionnaire.id)
        .where(Questionnaire.workspace_id == ws_id, Questionnaire.source == "csf", Run.status == "done")
        .order_by(func.coalesce(Run.finished_at, Run.started_at).desc(), Run.id)
        .limit(1)
    ).first()
    return (found[0], found[1]) if found else None


def _questionnaire(session: Session, ws_id: uuid.UUID, scope: str) -> Questionnaire | None:
    """The scope's built-in questionnaire under the CSF data deployed now, if a run ever made it."""
    return session.scalars(
        select(Questionnaire)
        .where(
            Questionnaire.workspace_id == ws_id,
            Questionnaire.source == "csf",
            Questionnaire.mapping.contains(csf.current_mapping(scope)),
        )
        .order_by(Questionnaire.created_at.desc())
    ).first()


@router.get("/api/gap/{scope}")
def gap_view(scope: GapScope, ws: WorkspaceDep, session: SessionDep) -> GapOut:
    """Every outcome of the scope's functions in NIST's order (the core: all 106), each with its tier and,
    once the latest run of the scope's current questionnaire has answered it, its gap label and explanation.
    Labels are decided by code; a not-checked outcome never carries one, nor does one the visitor marked not
    applicable (`not_applicable`) or one whose model call failed twice. Writes nothing; no model call."""
    q = _questionnaire(session, ws.id, scope)
    run = latest_run(session, q.id) if q is not None else None
    fw = csf.framework()
    return GapOut(
        scope=scope,
        csf_version=fw.version,
        retrieved=fw.retrieved,
        controls_url=csf.CONTROLS_URL,
        run=run_out(session, run) if run is not None else None,
        rows=gap_rows(session, scope, q, run),
    )


@router.post("/api/gap/{scope}/run")
def start_gap(scope: GapScope, ws: WorkspaceDep, session: SessionDep, request: Request) -> RunOut:
    """Start or continue the gap check for this scope, then call POST /api/runs/{id}/step while `running`.
    Creates (or reuses) the workspace's built-in questionnaire for the scope; it is never counted, listed or
    deleted with the visitor's questionnaires. Answers a new run when none exists on it, the running one, or
    the done one with every outcome whose evidence changed since (a new upload) re-opened, all of its parts;
    with nothing changed it stays done and no model is called. 429 per network (`run`, 20 an hour); 503 when
    the demo is full. Two presses at once answer the same run (the questionnaire is locked first)."""
    ws_id = ws.id
    limit(request, session, "run")
    ensure_capacity(session)
    q = csf.questionnaire_for(session, ws_id, scope)  # commits, releasing its lock
    # Lock the questionnaire so two first presses at once make one run (adversary-1 I2); create_run only
    # takes it FOR SHARE. The lock is held through create_run's commit.
    session.execute(select(Questionnaire.id).where(Questionnaire.id == q.id).with_for_update())
    run = latest_run(session, q.id)
    if run is None:
        run = create_run(session, ws_id, q.id, get_settings().models())
    return run_out(session, run)

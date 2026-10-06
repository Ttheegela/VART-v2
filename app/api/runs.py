"""Runs and the step runner (spec 6.3). Owner: lane 3A-runs (Task 8)."""

import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select, update

from app.api.deps import LLMDep, SessionDep, WorkspaceDep
from app.api.errors import NotFound, limit, network
from app.api.schemas import (
    ERRORS,
    SENTENCE_422,
    AnswerSummary,
    ApprovedCount,
    ItemOut,
    RunOut,
    RunRow,
    RunRowsOut,
    StepOut,
)
from app.db.models import Answer, Item, Run, RunItem
from app.runs import create_run as start_run
from app.runs import step
from app.services import audit_log
from app.services.capacity import ensure_capacity
from app.settings import get_settings

router = APIRouter(tags=["runs"], responses=ERRORS)


def summary(a: Answer) -> AnswerSummary:
    docs = {c["document_id"] for c in a.citations}
    return AnswerSummary(
        id=a.id,
        item_id=a.item_id,
        label=a.label,
        value=a.value,
        text=a.text,
        confidence=a.confidence,
        sources=1 if a.label == "user_confirmed" else len(docs),
        approved=a.approved_at is not None,
        edited=a.edited,
        statement_id=a.statement_id,
    )


def row(item: Item, answer: Answer | None) -> RunRow:
    return RunRow(item=ItemOut.model_validate(item), answer=summary(answer) if answer else None)


def run_out(session: SessionDep, run: Run) -> RunOut:
    total, done = session.execute(
        select(func.count(), func.count().filter(RunItem.state == "done")).where(RunItem.run_id == run.id)
    ).one()
    return RunOut(
        id=run.id,
        questionnaire_id=run.questionnaire_id,
        status=run.status,
        total=total,
        done=done,
        cost_usd=float(run.cost_usd),
        models=run.models,
        prompt_versions=run.prompt_versions,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _own(session: SessionDep, ws: WorkspaceDep, run_id: uuid.UUID) -> Run:
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == ws.id))
    if run is None:
        raise NotFound()
    return run


def _rows(session: SessionDep, run: Run, item_ids: list[uuid.UUID] | None = None) -> list[RunRow]:
    query = (
        select(Item, Answer)
        .outerjoin(Answer, (Answer.item_id == Item.id) & (Answer.run_id == run.id))
        .where(Item.questionnaire_id == run.questionnaire_id)
        .order_by(Item.position)
    )
    if item_ids is not None:
        query = query.where(Item.id.in_(item_ids))
    return [row(i, a) for i, a in session.execute(query)]


@router.post("/api/questionnaires/{questionnaire_id}/runs", status_code=201, responses=SENTENCE_422)
def create_run(
    questionnaire_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep, request: Request
) -> RunOut:
    """A new run over every item, all pending. 422 when the questionnaire has no items yet; 429 per network
    (`run`, 20 an hour); 503 when the demo is full."""
    limit(request, session, "run")
    ensure_capacity(session)
    return run_out(session, start_run(session, ws.id, questionnaire_id, get_settings().models()))


@router.post("/api/runs/{run_id}/step")
def step_run(
    run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep, request: Request, llm: LLMDep
) -> StepOut:
    """Claim up to 4 pending items, answer them, write one answer each. Call again while status is
    `running` (a step may answer nothing while another step holds the rest: wait a moment first). 429 with
    Retry-After when the network (`llm`, 400 model calls an hour, counted per call by the spender) or a model
    budget (workspace hour, global hour, global day) is used up; the sentence names which. 503 when model
    calls are off, or the provider is failing (a bad key, no credit, a rate limit, an outage): nothing is
    marked failed, the items stay pending and Retry-After says when to ask again."""
    ws_id = ws.id
    run = _own(session, ws, run_id)
    if llm is None:
        raise HTTPException(503, "Model calls are off right now; the sample's answers are still here.")
    answered = step(session, ws_id, run.id, llm, get_settings().models(), network=network(request))
    session.refresh(run)
    return StepOut(run=run_out(session, run), answered=_rows(session, run, answered) if answered else [])


@router.get("/api/runs/{run_id}")
def get_run(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> RunOut:
    return run_out(session, _own(session, ws, run_id))


@router.get("/api/runs/{run_id}/answers")
def run_answers(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> RunRowsOut:
    """Every item with its answer (None while pending), in questionnaire order."""
    run = _own(session, ws, run_id)
    return RunRowsOut(run=run_out(session, run), rows=_rows(session, run))


@router.post("/api/runs/{run_id}/approve-verified")
def approve_verified(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> ApprovedCount:
    """Approve every verified answer not yet approved (design key A). An edited answer is left for a look
    (adversary-1 M5): approve it by itself; `skipped_edited` counts them."""
    run = _own(session, ws, run_id)
    open_verified = (
        Answer.run_id == run.id,
        Answer.label == "verified",
        Answer.edited.is_(False),
        Answer.approved_at.is_(None),
    )
    # lock in id order first, as redecide does, so the two bulk lockers cannot deadlock (task-6 review M2)
    ids = session.scalars(select(Answer.id).where(*open_verified).order_by(Answer.id).with_for_update()).all()
    result = session.execute(
        update(Answer).where(Answer.id.in_(ids), *open_verified).values(approved_at=func.now())
    )
    n = int(result.rowcount or 0)  # type: ignore[attr-defined]
    skipped = session.scalar(
        select(func.count()).where(
            Answer.run_id == run.id,
            Answer.label == "verified",
            Answer.edited.is_(True),
            Answer.approved_at.is_(None),
        )
    )
    audit_log.record(session, ws.id, "answer.approve_verified", ref=str(run.id), detail={"approved": n})
    session.commit()
    return ApprovedCount(approved=n, skipped_edited=skipped or 0)

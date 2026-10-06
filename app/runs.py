"""Fill runs (spec 6.3): a run lists its items as run_items; each POST /api/runs/{id}/step claims up to
STEP_ITEMS of them in a short transaction (FOR UPDATE SKIP LOCKED), answers them outside any transaction, and
writes one answer row per item (UNIQUE (run_id, item_id): a duplicate write does nothing). No queue, no
worker: the browser drives the loop."""

import logging
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import NotFound
from app.classify import PROMPT_VERSION as CLASSIFY_PROMPT
from app.contracts import BudgetExhausted, ItemInput, ItemResult, Spend, jsonable
from app.db.models import Answer, Item, Questionnaire, Run, RunItem
from app.draft import PROMPT_VERSION as DRAFT_PROMPT
from app.ingest.parse import IngestError
from app.llm.client import LLMClient, LLMError, LLMRequest, LLMResult
from app.llm.recorder import ReplayMiss
from app.pipeline import answer_item
from app.services import audit_log
from app.services.llm_budget import Refused, refusal_scope, spender
from app.stance import PROMPT_VERSION as STANCE_PROMPT

log = logging.getLogger(__name__)

STEP_ITEMS = 4  # spec 6.3: N about 4; p50 is about 10 s an item (Plan 2 baseline)
STALE = timedelta(
    minutes=5
)  # a claim this old belongs to a crashed step (DEADLINE_S keeps live ones younger)
DEADLINE_S = 240.0  # under Vercel's 300 s function limit, as in PriorPath
MAX_ATTEMPTS = 3  # claims before an item that keeps crashing its step is answered as failed
FAILED_TEXT = "No answer: the model call failed twice. Re-run live to try again."


class CostMeter:
    """Counts the cost of every result the client returns, even when the caller then fails to use it (a
    reply that does not match the schema is still billed: triage rows 16 and 51)."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self._cost = 0.0

    def complete(self, req: LLMRequest) -> LLMResult:
        result = self.inner.complete(req)
        self._cost += result.cost_usd or 0.0
        return result

    def take(self) -> float:
        cost, self._cost = self._cost, 0.0
        return cost


def _run(session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id))
    if run is None:
        raise NotFound()
    return run


def create_run(
    session: Session, workspace_id: uuid.UUID, questionnaire_id: uuid.UUID, models: Mapping[str, str]
) -> Run:
    q = session.scalar(
        select(Questionnaire).where(
            Questionnaire.id == questionnaire_id, Questionnaire.workspace_id == workspace_id
        )
    )
    if q is None:
        raise NotFound()
    item_ids = list(
        session.scalars(select(Item.id).where(Item.questionnaire_id == q.id).order_by(Item.position))
    )
    if not item_ids:
        raise IngestError("Confirm the column mapping first: this questionnaire has no questions yet.")
    run = Run(
        workspace_id=workspace_id,
        questionnaire_id=q.id,
        prompt_versions={"stance": STANCE_PROMPT, "draft": DRAFT_PROMPT, "classify": CLASSIFY_PROMPT},
        models=dict(models),
    )
    session.add(run)
    session.flush()
    session.execute(insert(RunItem), [{"run_id": run.id, "item_id": i} for i in item_ids])
    audit_log.record(session, workspace_id, "run.create", ref=str(run.id), detail={"items": len(item_ids)})
    session.commit()
    return run


def _claim(session: Session, run_id: uuid.UUID, now: datetime) -> list[tuple[uuid.UUID, int]]:
    """(item id, attempts before this claim), in questionnaire order; committed before any model call."""
    rows = session.execute(
        select(RunItem.item_id, RunItem.attempts)
        .join(Item, Item.id == RunItem.item_id)
        .where(
            RunItem.run_id == run_id,
            or_(
                RunItem.state == "pending", and_(RunItem.state == "claimed", RunItem.claimed_at < now - STALE)
            ),
        )
        .order_by(Item.position)
        .limit(STEP_ITEMS)
        .with_for_update(skip_locked=True, of=RunItem)
    ).all()
    if rows:
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id.in_([r.item_id for r in rows]))
            .values(state="claimed", claimed_at=now, attempts=RunItem.attempts + 1)
        )
    session.commit()
    return [(r.item_id, r.attempts) for r in rows]


def _release(session: Session, run_id: uuid.UUID, item_ids: list[uuid.UUID]) -> None:
    if item_ids:
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id.in_(item_ids), RunItem.state == "claimed")
            .values(state="pending", claimed_at=None)
        )
    session.commit()


def _answer(
    session: Session,
    workspace_id: uuid.UUID,
    item: ItemInput,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult:
    """One item, retried once on a failed model call (a malformed reply rarely repeats). Never retries a
    missing recording or a refused budget. Plan 6B branches here on the questionnaire's source."""
    try:
        return answer_item(session, workspace_id, item, llm, models, spend)
    except (ReplayMiss, BudgetExhausted):
        raise
    except LLMError:
        session.rollback()
        return answer_item(session, workspace_id, item, llm, models, spend)


def _values(r: ItemResult) -> dict[str, Any]:
    d = r.decision
    return {
        "label": d.label,
        "value": d.value,
        "text": r.draft.text,
        "citations": jsonable(d.citations),
        "dropped": jsonable(d.dropped),
        "conflict": jsonable(d.conflict),
        "scope_note": d.scope_note,
        "confidence": d.confidence,
        "stances": jsonable(r.stances),
        "chunk_ids": [p.chunk_id for p in r.retrieval.passages],
        "retrieval_dropped": jsonable(r.retrieval.dropped),
    }


FAILED: dict[str, Any] = {"label": "unknown", "value": None, "text": FAILED_TEXT, "confidence": 0.0}


def _add_cost(session: Session, run_id: uuid.UUID, cost: float) -> None:
    if cost:
        session.execute(
            update(Run).where(Run.id == run_id).values(cost_usd=Run.cost_usd + Decimal(str(round(cost, 6))))
        )


def _write(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    values: dict[str, Any],
    cost: float,
) -> None:
    session.execute(
        insert(Answer)
        .values(workspace_id=workspace_id, run_id=run_id, item_id=item_id, **values)
        .on_conflict_do_nothing(constraint="uq_answers_run_item")
    )
    session.execute(
        update(RunItem).where(RunItem.run_id == run_id, RunItem.item_id == item_id).values(state="done")
    )
    _add_cost(session, run_id, cost)
    session.commit()


def _finish_if_done(session: Session, run: Run) -> None:
    left = session.scalar(
        select(RunItem.item_id).where(RunItem.run_id == run.id, RunItem.state != "done").limit(1)
    )
    if left is None:
        closed = session.scalar(
            update(Run)
            .where(Run.id == run.id, Run.status == "running")
            .values(status="done", finished_at=datetime.now(UTC))
            .returning(Run.id)
        )
        if closed:  # only the step that closes the run records it
            audit_log.record(session, run.workspace_id, "run.done", ref=str(run.id))
    session.commit()
    session.refresh(run)


def step(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    llm: LLMClient,
    models: Mapping[str, str],
    *,
    clock: Callable[[], float] = time.monotonic,
    now: datetime | None = None,
    network: str | None = None,
) -> list[uuid.UUID]:
    """Answer up to STEP_ITEMS items; returns the item ids answered. Raises BudgetExhausted (a
    `llm_budget.Refused` naming the cap; unstarted items go back to pending) and ReplayMiss (never degraded,
    contract rule). `network` is `errors.network(request)`: the spender counts each call."""
    run = _run(session, workspace_id, run_id)
    if run.status != "running":
        return []
    deadline = clock() + DEADLINE_S
    claimed = _claim(session, run_id, now or datetime.now(UTC))
    meter = CostMeter(llm)
    spend = spender(session, workspace_id, network=network)
    answered: list[uuid.UUID] = []
    for n, (item_id, attempts) in enumerate(claimed):
        rest = [i for i, _ in claimed[n:]]
        if clock() > deadline:
            _release(session, run_id, rest)
            break
        if attempts >= MAX_ATTEMPTS:
            _write(session, workspace_id, run_id, item_id, FAILED, 0.0)
            answered.append(item_id)
            continue
        row = session.get_one(Item, item_id)
        item = ItemInput(str(row.id), row.question, row.topic)
        try:
            values = _values(_answer(session, workspace_id, item, meter, models, spend))
        except (BudgetExhausted, ReplayMiss) as exc:
            session.rollback()
            refused: BudgetExhausted | None = None
            if isinstance(exc, BudgetExhausted):
                kind = str(exc.args[0]) if exc.args else "stance"
                scope = (
                    exc.scope
                    if isinstance(exc, Refused)
                    else refusal_scope(session, workspace_id, kind, network)
                )
                refused = Refused(kind, scope)
            _release(session, run_id, rest)
            _add_cost(session, run_id, meter.take())
            session.commit()
            raise (refused or exc) from None
        except LLMError:
            session.rollback()
            values = FAILED
        except SQLAlchemyError:
            session.rollback()  # triage row 24: a failed transaction must not swallow the next write
            log.exception("run %s item %s: database error; answered as failed", run_id, item_id)
            values = FAILED
        _write(session, workspace_id, run_id, item_id, values, meter.take())
        answered.append(item_id)
    _finish_if_done(session, run)
    return answered

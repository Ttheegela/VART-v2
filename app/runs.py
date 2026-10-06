"""Fill runs (spec 6.3): a run lists its items as run_items; each POST /api/runs/{id}/step claims up to
STEP_ITEMS of them in a short transaction (FOR UPDATE SKIP LOCKED), answers them outside any transaction, and
writes one answer row per item (UNIQUE (run_id, item_id): a duplicate write does nothing). No queue, no worker
process: the browser drives the loop. A step answers its claimed items, or a gap check's parts, at the same
time on a small thread pool, each job on its own session, spender and cost meter (Plan 4 Task 2); a gap-check
step claims outcomes by their parts (CSF spec 5.7) and stores each part as it lands."""

import logging
import random
import time
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

import openai
from sqlalchemy import Engine, and_, delete, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import DataError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import csf
from app.api.errors import Conflict, ModelsUnavailable, NotFound, retry_after_budget
from app.classify import PROMPT_VERSION as CLASSIFY_PROMPT
from app.contracts import BudgetExhausted, ItemInput, ItemResult, Spend, jsonable
from app.db.models import Answer, Item, Questionnaire, Run, RunItem, SuggestedFill, Workspace
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
# a step answers by then whatever its jobs do: under Vercel's 300 s, so STALE never meets a live step
HARD_S = 270.0
MAX_ATTEMPTS = 3  # claims before an item that keeps crashing its step is answered as failed
ABANDONED = timedelta(minutes=10)  # a running run no step touched this long was left (a closed tab): Ruling 8
RUN_IN_PROGRESS = "A run of this questionnaire is still going; wait for it to finish first."
FAILED_TEXT = "No answer: the model call failed twice. Re-run live to try again."
STEP_PARTS = 8  # CSF spec 5.7: a gap-check step claims outcomes until their parts add up to 8 (8 x 15 s p90)
# An Ask-me outcome waits for the visitor (CSF spec 5.4): no retrieval, no call; gap_label shows Not answered.
ASK: dict[str, Any] = {"label": "unknown", "value": None, "text": "", "confidence": 0.0}


class CostMeter:
    """Counts the cost of every result the client returns, even when the caller then fails to use it (a
    reply that does not match the schema is still billed: triage rows 16 and 51), and how many returned
    (`calls`: the provider answered, Task 2 re-review I1)."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self._cost = 0.0
        self.calls = 0

    def complete(self, req: LLMRequest) -> LLMResult:
        result = self.inner.complete(req)
        self._cost += result.cost_usd or 0.0
        self.calls += 1
        return result

    def take(self) -> float:
        cost, self._cost = self._cost, 0.0
        return cost


def _run(session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id))
    if run is None:
        raise NotFound()
    return run


def close_abandoned(
    session: Session, workspace_id: uuid.UUID, questionnaire_id: uuid.UUID | None = None
) -> int:
    """Close the workspace's running runs that no step touched for ABANDONED as `failed`, so they block
    neither a new run nor a document delete (Plan 3 Ruling 8; PROGRESS carry-over). One UPDATE: a step that
    touches a run at the same moment wins, because the row lock re-checks the condition. Does not commit.
    Lock order: the workspace row FOR KEY SHARE, then the run rows, then the audit rows (which point at the
    workspace). So a reset (workspace FOR UPDATE, then a cascade to the runs) waits or goes first, and Task
    5's writers (workspace FOR NO KEY UPDATE, which KEY SHARE does not wait for, and no run row lock) never
    wait for a run row this holds: no cycle with either."""
    session.execute(
        select(Workspace.id).where(Workspace.id == workspace_id).with_for_update(read=True, key_share=True)
    )
    stmt = (
        update(Run)
        .where(
            Run.workspace_id == workspace_id,
            Run.status == "running",
            func.coalesce(Run.stepped_at, Run.started_at) < func.now() - ABANDONED,
        )
        .values(status="failed", finished_at=func.now())
        .returning(Run.id)
    )
    if questionnaire_id is not None:
        stmt = stmt.where(Run.questionnaire_id == questionnaire_id)
    closed = list(session.scalars(stmt))
    for run_id in closed:
        audit_log.record(session, workspace_id, "run.abandoned", ref=str(run_id))
    return len(closed)


def create_run(
    session: Session, workspace_id: uuid.UUID, questionnaire_id: uuid.UUID, models: Mapping[str, str]
) -> Run:
    q = session.scalar(
        select(Questionnaire)
        .where(Questionnaire.id == questionnaire_id, Questionnaire.workspace_id == workspace_id)
        .with_for_update()  # two creates, a mapping change or a delete take turns (Plan 4 Task 4)
    )
    if q is None:
        raise NotFound()
    close_abandoned(session, workspace_id, q.id)
    if session.scalar(select(exists().where(Run.questionnaire_id == q.id, Run.status == "running"))):
        raise Conflict(RUN_IN_PROGRESS)  # one live run per questionnaire: two would pay twice (Ruling 8)
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


def _claim(
    session: Session, run_id: uuid.UUID, now: datetime, *, by_parts: bool = False
) -> list[tuple[uuid.UUID, int]]:
    """(item id, attempts before this claim), in questionnaire order; committed before any model call. A
    questionnaire step takes STEP_ITEMS items. A gap-check step takes outcomes until their parts add up to
    STEP_PARTS (CSF spec 5.7): an outcome with more is taken alone, and an Ask-me outcome counts one."""
    rows = list(
        session.execute(
            select(RunItem.item_id, RunItem.attempts, Item.csf_id)
            .join(Item, Item.id == RunItem.item_id)
            .where(
                RunItem.run_id == run_id,
                or_(
                    RunItem.state == "pending",
                    and_(RunItem.state == "claimed", RunItem.claimed_at < now - STALE),
                ),
            )
            .order_by(Item.position)
            .limit(STEP_PARTS if by_parts else STEP_ITEMS)
            .with_for_update(skip_locked=True, of=RunItem)
        ).all()
    )
    if by_parts:
        rows = _by_parts(rows)
    if rows:
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id.in_([r.item_id for r in rows]))
            .values(state="claimed", claimed_at=now, attempts=RunItem.attempts + 1)
        )
    session.commit()  # rows locked but not taken are free again
    return [(r.item_id, r.attempts) for r in rows]


def _by_parts(rows: list[Any]) -> list[Any]:
    """The leading rows whose parts fit STEP_PARTS (at least one). An id the data no longer has weighs one."""
    taken: list[Any] = []
    total = 0
    for r in rows:
        o = csf.outcome_or_none(r.csf_id or "")
        weight = max(1, len(o.parts)) if o else 1
        if taken and total + weight > STEP_PARTS:
            break
        taken.append(r)
        total += weight
    return taken


def _release(session: Session, run_id: uuid.UUID, item_ids: list[uuid.UUID], *, refund: bool = True) -> None:
    if item_ids:
        # the claim counted an attempt, but a released item was never tried: give it back (review C1).
        # refund=False keeps it for the item that met a provider error, so MAX_ATTEMPTS still binds.
        attempts = func.greatest(RunItem.attempts - 1, 0) if refund else RunItem.attempts
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id.in_(item_ids), RunItem.state == "claimed")
            .values(state="pending", claimed_at=None, attempts=attempts)
        )
    session.commit()


def _retryable(exc: LLMError) -> bool:
    """Transport errors, 5xx and a reply that fails the schema repeat rarely; a 4xx (bad key, no credit, bad
    request) repeats every time and would spend a second unit of budget for nothing. A timeout (408) or a
    rate limit (429) passes."""
    status = getattr(exc.__cause__, "status_code", None)
    return not (isinstance(status, int) and 400 <= status < 500 and status not in (408, 429))


class _DeadlineCut(LLMError):
    """A retryable model error whose single retry the step's deadline cut (adversary-1 M2): decided when the
    retry was refused, not when the step settles. Its cause is the original error's, so `_provider_down` and
    `_retryable` read it the same."""


def _retry_pause(exc: LLMError) -> float:
    """Seconds to wait before retrying: a short pause on a rate limit (429), so a step's workers do not
    re-fire their calls in the same second (adversary-1 I3): Retry-After (else 1 s) plus up to 0.5 s of
    jitter, at most 2 s. No wait otherwise."""
    cause = exc.__cause__
    if getattr(cause, "status_code", None) != 429:
        return 0.0
    try:
        after = max(0.0, float(cause.response.headers.get("retry-after", "")))  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        after = 1.0
    return min(2.0, after + random.uniform(0.0, 0.5))


def _once[T](session: Session, call: Callable[[], T], can_retry: Callable[[], bool]) -> T:
    """`call`, and once more after a failed model call (a malformed reply rarely repeats), after a short pause
    on a rate limit (`_retry_pause`). Never again on a missing recording or a refused budget, nor once
    `can_retry` says the step's deadline has passed (`_DeadlineCut`)."""
    try:
        return call()
    except (ReplayMiss, BudgetExhausted):
        raise
    except LLMError as exc:
        if not _retryable(exc):
            raise
        if not can_retry():
            raise _DeadlineCut(*exc.args) from exc.__cause__
        session.rollback()
        if pause := _retry_pause(exc):
            time.sleep(pause)
        return call()


def _answer(
    session: Session,
    workspace_id: uuid.UUID,
    item: ItemInput,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
    can_retry: Callable[[], bool] = lambda: True,
) -> ItemResult:
    """One questionnaire item, retried once on a failed model call (`_once`)."""
    return _once(session, partial(answer_item, session, workspace_id, item, llm, models, spend), can_retry)


@dataclass
class _Done:
    """One job's result: the values to write (None for a part job, or on an error), its cost, its error, and
    how many of its model calls returned."""

    values: dict[str, Any] | None
    cost: float
    error: Exception | None = None
    calls: int = 0


class _Late(Exception):
    """A job still running at HARD_S: the step answered without it (Plan 3 N1)."""


def _session(engine: Engine) -> Session:
    """A worker's own session: a Session never crosses threads (Plan 4 Task 2)."""
    return Session(engine, expire_on_commit=False)


def _item_job(
    engine: Engine,
    workspace_id: uuid.UUID,
    item: ItemInput,
    llm: LLMClient,
    models: Mapping[str, str],
    network: str | None,
    can_retry: Callable[[], bool],
) -> _Done:
    """One questionnaire item on a worker thread: its own session, spender and cost meter. Every error comes
    back to the request's thread with the cost already paid."""
    meter = CostMeter(llm)
    try:
        with _session(engine) as s:
            spend = spender(s, workspace_id, network=network)
            result = _answer(s, workspace_id, item, meter, models, spend, can_retry)
            return _Done(_values(result), meter.take(), calls=meter.calls)
    except Exception as exc:
        return _Done(None, meter.take(), exc, meter.calls)


def _part_job(
    engine: Engine,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    claimed_at: datetime,
    o: csf.Outcome,
    n: int,
    llm: LLMClient,
    models: Mapping[str, str],
    network: str | None,
    can_retry: Callable[[], bool],
) -> _Done:
    """Part n of a gap-check outcome on a worker thread, stored the moment it lands (CSF spec 5.7) with one
    atomic `parts || {n: part}`, so two parts of one outcome finishing together never lose each other. Only
    while this step's claim holds (adversary-1 M1): a part landing after the step answered without it (late),
    or after a release, a reclaim or Check again, touches no row; the next step runs it again."""
    meter = CostMeter(llm)
    try:
        with _session(engine) as s:
            spend = spender(s, workspace_id, network=network)
            r = _once(s, partial(csf.check_part, s, workspace_id, o, n, meter, models, spend), can_retry)
            judged = {"question": o.parts[n - 1], "stance_prompt": STANCE_PROMPT, "model": models["stance"]}
            part = _no_nul({**judged, **_raw(r)})
            s.execute(
                update(RunItem)
                .where(
                    RunItem.run_id == run_id,
                    RunItem.item_id == item_id,
                    RunItem.state == "claimed",
                    RunItem.claimed_at == claimed_at,
                )
                .values(parts=RunItem.parts.op("||")(literal({str(n): part}, JSONB)))
            )
            s.commit()
            return _Done(None, meter.take(), calls=meter.calls)
    except Exception as exc:
        return _Done(None, meter.take(), exc, meter.calls)


def _keep_current_parts(
    session: Session, run_id: uuid.UUID, item_id: uuid.UUID, o: csf.Outcome, models: Mapping[str, str]
) -> list[int]:
    """Drop stored parts that no longer stand for the deployed wording, stance prompt and model
    (`_is_current`, adversary-1 M5); return the part numbers still to run. Does not commit."""
    have = (
        session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == item_id))
        or {}
    )
    keep = {k: v for k, v in have.items() if k.isdigit() and _is_current(o, int(k), v, models)}
    if keep != have:
        session.execute(
            update(RunItem).where(RunItem.run_id == run_id, RunItem.item_id == item_id).values(parts=keep)
        )
    return [n for n in range(1, len(o.parts) + 1) if str(n) not in keep]


def _run_all(
    jobs: dict[uuid.UUID, list[Callable[[], _Done]]], in_time: Callable[[], bool], hard_at: float
) -> dict[uuid.UUID, list[_Done | None]]:
    """Every job at once, at most STEP_PARTS workers. A job that would start after the deadline is not started
    (None); a job still running at `hard_at` (time.monotonic) is late (`_Late`) and the pool is left behind
    without waiting for it. Results come back per item in the order the jobs were listed."""

    def guarded(job: Callable[[], _Done]) -> _Done | None:
        try:
            ok = in_time()
        except Exception as exc:  # a broken clock is this job's error, not the step's (review M1)
            return _Done(None, 0.0, exc)
        return job() if ok else None

    out: dict[uuid.UUID, list[_Done | None]] = {item_id: [] for item_id in jobs}
    flat = [(item_id, job) for item_id, listed in jobs.items() for job in listed]
    if not flat:
        return out
    pool = ThreadPoolExecutor(max_workers=min(len(flat), STEP_PARTS))
    futures = [(item_id, pool.submit(guarded, job)) for item_id, job in flat]
    wait([fut for _, fut in futures], timeout=max(0.0, hard_at - time.monotonic()))
    pool.shutdown(wait=False, cancel_futures=True)
    for item_id, fut in futures:
        if fut.cancelled():
            out[item_id].append(None)  # never started: as if the deadline kept it
        elif fut.done():
            out[item_id].append(fut.result())
        else:
            out[item_id].append(_Done(None, 0.0, _Late()))
    return out


def _worst(errors: list[Exception]) -> Exception:
    """An item's most decisive error: a missing recording, a refused budget, a late job, a provider outage,
    then the first of the rest."""
    for kind in (ReplayMiss, BudgetExhausted, _Late):
        for e in errors:
            if isinstance(e, kind):
                return e
    for e in errors:
        if isinstance(e, LLMError) and _provider_down(e):
            return e
    return errors[0]


def _stored(session: Session, run_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
    parts: dict[str, Any] = (
        session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == item_id))
        or {}
    )
    return parts


def _safe_write(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    values: dict[str, Any],
    cost: float,
) -> None:
    """The database refused a value: write the failure, not a reclaim loop."""
    try:
        _write(session, workspace_id, run_id, item_id, values, cost)
    except DataError as exc:
        session.rollback()
        log.error("run %s item %s: %s on write; answered as failed", run_id, item_id, type(exc).__name__)
        _write(session, workspace_id, run_id, item_id, FAILED, cost)


def _is_current(o: csf.Outcome, n: int, raw: Mapping[str, Any], models: Mapping[str, str]) -> bool:
    """A stored part still stands for part n as deployed: the same wording, judged by the same stance prompt
    and model (adversary-1 M5). A part filled from the visitor's answer has no judge of its own; only its
    wording counts."""
    if not 1 <= n <= len(o.parts) or raw.get("question") != o.parts[n - 1]:
        return False
    judged = (raw.get("stance_prompt"), raw.get("model")) == (STANCE_PROMPT, models["stance"])
    return judged or bool(raw.get("statement_id"))


def outcome_values(o: csf.Outcome, parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """A Checked outcome's answer row from its stored parts, all present (CSF spec 5.3): the label by
    `combine`, code's explanation, the parts' citations and drops. Its chunk ids are the parts' union, so a
    metadata override finds it (app.redecide decides it again part by part); no stances of its own. Parts
    filled from the visitor's answer are named first in the explanation (`csf.explain`), and an outcome that
    would read Covered with any of them is Confirmed by you, citing the first one's statement (Ruling 6:
    with a Gap or Partly part left it stays Partly covered)."""
    raws = [parts[str(n)] for n in range(1, len(o.parts) + 1)]
    results = [csf.part_result(o, n, r) for n, r in enumerate(raws, 1)]
    values = _values(csf.aggregate(o, results))
    values["chunk_ids"] = list(dict.fromkeys(c for r in raws for c in r["chunk_ids"]))
    filled = [n for n, r in enumerate(raws, 1) if r.get("statement_id")]
    values["statement_id"] = None
    if filled:
        values["text"] = _no_nul(csf.explain(o, results, filled))
        if (values["label"], values["value"]) == ("verified", "Yes"):
            values |= {"label": "user_confirmed", "value": None}
            values["statement_id"] = uuid.UUID(raws[filled[0] - 1]["statement_id"])
    return values


def _no_nul(v: Any) -> Any:
    """Postgres refuses U+0000 in text and jsonb; a model reply (or a document it quotes) can carry one."""
    if isinstance(v, str):
        return v.replace("\x00", "")
    if isinstance(v, list):
        return [_no_nul(x) for x in v]
    if isinstance(v, dict):
        return {k: _no_nul(x) for k, x in v.items()}
    return v


def _provider_down(exc: LLMError) -> bool:
    """The provider, not the model's answer, failed: bad key (401), no credit (402), timeout (408), rate limit
    (429), 5xx, a dropped connection. A reply that fails the schema, or another 4xx, is a bad answer."""
    cause = exc.__cause__
    if not isinstance(cause, openai.APIError):
        return False
    status = getattr(cause, "status_code", None)
    return not isinstance(status, int) or status in (401, 402, 408, 429) or status >= 500


def _values(r: ItemResult) -> dict[str, Any]:
    clean: dict[str, Any] = _no_nul(_raw(r))
    return clean


def _raw(r: ItemResult) -> dict[str, Any]:
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


def _keep_cost(
    session: Session, run_id: uuid.UUID, cost: float, unstarted: list[tuple[uuid.UUID, int]]
) -> None:
    """An unexpected error: the calls already paid for still count. The item that failed stays claimed with
    its attempt counted (a crash loop ends at MAX_ATTEMPTS); the items not yet started go back."""
    session.rollback()
    _add_cost(session, run_id, cost)
    _release(session, run_id, [i for i, _ in unstarted])  # commits


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
    """Answer the claimed items at once (Plan 4 Task 2): up to STEP_ITEMS questionnaire items, or the parts of
    gap-check outcomes up to STEP_PARTS, each job on a worker thread with its own session, spender and cost
    meter, spending before every model call and holding no transaction across one. A job starts, or retries,
    only before DEADLINE_S (`clock`); the step answers by HARD_S in real time. Then, on this thread in
    questionnaire order: write every answer that came back (one row per item; a duplicate write does nothing),
    count every paid call, give back the items that met a refusal, a missing recording or the deadline
    (attempt refunded), and those that met an outage or were late (attempt kept). When no model call returned
    in the step (an answer with no call shows nothing about the provider), only the first item that met the
    outage keeps its attempt and the others are refunded (Ruling 5); a late job's stays. An item whose write
    fails stays claimed with its attempt and cost counted, and the others are still settled. Raises, after the
    writes: ReplayMiss, then a `llm_budget.Refused` naming the cap, then an unexpected error (its item stays
    claimed), then ModelsUnavailable when no model call returned. Returns the item ids answered. `network` is
    `errors.network(request)`: each spender counts each call for it."""
    run = _run(session, workspace_id, run_id)
    if run.status != "running":
        return []
    touched = session.scalar(  # committed by _claim
        update(Run)
        .where(Run.id == run_id, Run.status == "running")
        .values(stepped_at=func.now())
        .returning(Run.id)
    )
    if touched is None:  # closed as abandoned since the read (adversary-1 I2): a failed run is never stepped
        session.commit()
        return []
    by_parts = (
        session.scalar(select(Questionnaire.source).where(Questionnaire.id == run.questionnaire_id)) == "csf"
    )
    hard_at = time.monotonic() + HARD_S  # real time: it bounds real waiting, whatever `clock` says
    deadline = clock() + DEADLINE_S
    claimed_at = now or datetime.now(UTC)
    claimed = _claim(session, run_id, claimed_at, by_parts=by_parts)
    engine = session.get_bind()
    assert isinstance(engine, Engine)

    def in_time() -> bool:
        return clock() <= deadline

    jobs: dict[uuid.UUID, list[Callable[[], _Done]]] = {}
    ready: dict[uuid.UUID, dict[str, Any]] = {}  # answered with no model call
    outcomes: dict[uuid.UUID, csf.Outcome] = {}
    for n, (item_id, attempts) in enumerate(claimed):
        try:
            if attempts >= MAX_ATTEMPTS:
                ready[item_id] = FAILED
                continue
            row = session.get_one(Item, item_id)
            # an id a data refresh withdrew is answered as the question it was (adversary-1 N1)
            o = csf.outcome_or_none(row.csf_id) if row.csf_id is not None else None
            if o is None:
                item = ItemInput(str(row.id), row.question, row.topic)
                jobs[item_id] = [
                    partial(_item_job, engine, workspace_id, item, llm, models, network, in_time)
                ]
            elif o.tier != "checked":
                ready[item_id] = dict(ASK)
            else:
                outcomes[item_id] = o
                jobs[item_id] = [
                    partial(
                        _part_job,
                        engine,
                        workspace_id,
                        run_id,
                        item_id,
                        claimed_at,
                        o,
                        k,
                        llm,
                        models,
                        network,
                        in_time,
                    )
                    for k in _keep_current_parts(session, run_id, item_id, o, models)
                ]
        except Exception:
            # nothing started: this item stays claimed, every other one goes back (preflight M4)
            _keep_cost(session, run_id, 0.0, claimed[:n] + claimed[n + 1 :])
            raise
    session.commit()  # the request's session holds no transaction while the workers call models
    results = _run_all(jobs, in_time, hard_at)

    answered: list[uuid.UUID] = []
    give_back: list[uuid.UUID] = []
    down: list[uuid.UUID] = []  # met an outage, in questionnaire order
    late: list[uuid.UUID] = []  # still running at HARD_S: the attempt stays
    replay: ReplayMiss | None = None
    refused: BudgetExhausted | None = None
    crashed: Exception | None = None
    for item_id, _ in claimed:
        done = results.get(item_id, [])
        cost = sum(d.cost for d in done if d is not None)
        errors = [d.error for d in done if d is not None and d.error is not None]
        try:
            if item_id in ready:
                _write(session, workspace_id, run_id, item_id, ready[item_id], 0.0)
                answered.append(item_id)
                continue
            if not errors and None not in done:
                values = (
                    outcome_values(outcomes[item_id], _stored(session, run_id, item_id))
                    if item_id in outcomes
                    else done[0].values  # type: ignore[union-attr]
                )
                _safe_write(session, workspace_id, run_id, item_id, values or FAILED, cost)
                answered.append(item_id)
                continue
            _add_cost(session, run_id, cost)
            session.commit()
            cost = 0.0  # counted
            if not errors:  # the deadline kept a job from starting: not tried, so no attempt spent
                give_back.append(item_id)
                continue
            err = _worst(errors)
            if isinstance(err, ReplayMiss):
                replay = replay or err
                give_back.append(item_id)
            elif isinstance(err, BudgetExhausted):
                refused = refused or err
                give_back.append(item_id)
            elif isinstance(err, _Late):
                late.append(item_id)
            elif isinstance(err, LLMError) and _provider_down(err):
                down.append(item_id)
            elif isinstance(err, _DeadlineCut):
                give_back.append(item_id)  # the deadline cut the retry: not tried twice, so not failed
            elif isinstance(err, (LLMError, SQLAlchemyError)):
                if isinstance(err, SQLAlchemyError):  # the type only: its parameters carry the words
                    log.error("run %s item %s: %s; answered as failed", run_id, item_id, type(err).__name__)
                _write(session, workspace_id, run_id, item_id, FAILED, 0.0)  # its cost is already added
                answered.append(item_id)
            else:
                crashed = crashed or err  # stays claimed, attempt counted: a crash loop ends at MAX_ATTEMPTS
        except Exception as exc:
            # the write failed: this item stays claimed with its attempt and its paid calls counted, and the
            # others are still settled, not given back to be paid again (adversary-1 M3)
            session.rollback()
            _add_cost(session, run_id, cost)
            session.commit()
            crashed = crashed or exc
    _release(session, run_id, give_back)
    # A model call returned in this step: the outage was selective, so each item that met it keeps its attempt
    # (adversary-3 N1). None did (an answer with no call, as Failed at MAX_ATTEMPTS, Ask me or a part with no
    # passage, shows nothing about the provider): only the first item that met it keeps its attempt and the
    # rest are refunded (Ruling 5, preflight I1), so a true outage costs at most one attempt a step and items
    # the provider always fails still end FAILED, one by one (Task 2 re-review I1).
    spoke = any(d.calls for listed in results.values() for d in listed if d is not None)
    first = down[:1] if not spoke else down
    _release(session, run_id, first, refund=False)
    _release(session, run_id, down[len(first) :])
    _release(session, run_id, late, refund=False)
    if replay is not None:
        raise replay
    if refused is not None:
        kind = str(refused.args[0]) if refused.args else "stance"
        scope = (
            refused.scope
            if isinstance(refused, Refused)
            else refusal_scope(session, workspace_id, kind, network)
        )
        # the step loop waits Retry-After with no step: the run reads as touched until then (preflight I5)
        wait = timedelta(seconds=retry_after_budget(scope=scope))
        session.execute(
            update(Run).where(Run.id == run_id, Run.status == "running").values(stepped_at=func.now() + wait)
        )
        session.commit()
        raise Refused(kind, scope) from None
    if crashed is not None:
        raise crashed
    if (down or late) and not spoke:
        raise ModelsUnavailable()  # when a call returned, the next step meets the outage itself
    _finish_if_done(session, run)
    return answered


REOPEN = ("verified", "partial", "conflict", "unknown")  # machine labels; the visitor's own labels stay


def machine_judged(labels: tuple[str, ...]) -> Any:
    """Answers with a machine label, or a Checked CSF outcome that reads Confirmed by you through a part fill:
    its other parts are still judged on the documents (review I2). An Ask-me confirmation has no parts.
    Used by Check again and by re-decide."""
    with_parts = (
        select(RunItem.item_id)
        .where(RunItem.run_id == Answer.run_id, RunItem.item_id == Answer.item_id, RunItem.parts != {})
        .exists()
    )
    return or_(Answer.label.in_(labels), and_(Answer.label == "user_confirmed", with_parts))


def _same_evidence(
    session: Session,
    workspace_id: uuid.UUID,
    o: csf.Outcome,
    n: int,
    raw: Mapping[str, Any],
    models: Mapping[str, str],
) -> bool:
    """A stored part still describes the documents: the deployed wording and judge (`_is_current`), and the
    same passages retrieved now, as a set: decide reads them by content, not rank (adversary-1 I4).
    Retrieval only, no model call."""
    if not _is_current(o, n, raw, models):
        return False
    found = csf.evidence(session, workspace_id, csf.part_inputs(o)[n - 1])
    return {p.chunk_id for p in found.passages} == set(raw["chunk_ids"])


def reopen_changed(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    models: Mapping[str, str] | None = None,
) -> int:
    """Check again after an upload (CSF spec 5.6; plan 6B decision 3), with no model call. A Checked outcome
    is affected when a stored part is missing, its wording, judge or evidence changed, or its answer failed.
    Every machine-judged part of an affected outcome is dropped, and the outcome goes back to pending with its
    answer removed and its whole-item fills dismissed, so the step loop runs all of its parts again. A part
    filled by a fill the visitor accepted stays, and so do the open per-part fills (a fill is the visitor's
    answer judged against the part's wording, not the documents), and an outcome the visitor edited,
    approved, confirmed (Ask me) or marked not applicable. A part's judge is compared with `models`, the
    deployed ones the next step uses (review I1; default: the run's own). Lock order: the run (two presses
    re-open once), the answers by id, then their run items, read under those locks so an accept in flight is
    waited out and its part kept (preflight I1), then the fills. ponytail: the evidence scan (one retrieval
    per stored part) runs under those locks, so a press blocks accepts and edits for it; fine at demo scale,
    scan first and re-verify under the locks if it is not. Returns the outcomes re-opened; with any, the run
    is running."""
    run = session.scalar(
        select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id).with_for_update()
    )
    if run is None or run.status != "done":
        session.commit()
        return 0
    answers = session.scalars(
        select(Answer)
        .join(Item, Item.id == Answer.item_id)
        .where(
            Answer.run_id == run_id,
            Item.csf_id.is_not(None),
            machine_judged(REOPEN),
            Answer.edited.is_(False),
            Answer.approved_at.is_(None),
        )
        .order_by(Answer.id)
        .with_for_update(of=Answer)
    ).all()
    judge = models or run.models
    failed = {a.item_id for a in answers if a.text == FAILED_TEXT}
    rows = session.execute(
        select(RunItem.item_id, RunItem.parts, Item.csf_id)
        .join(Item, Item.id == RunItem.item_id)
        .where(RunItem.run_id == run_id, RunItem.item_id.in_([a.item_id for a in answers]))
        .order_by(Item.position)
        .with_for_update(of=RunItem)
    ).all()  # fetched first: _same_evidence runs queries of its own
    reopened: dict[uuid.UUID, dict[str, Any]] = {}
    for item_id, stored, csf_id in rows:
        o = csf.outcome_or_none(csf_id or "")
        if o is None or o.tier != "checked":
            continue
        affected = (
            item_id in failed
            or any(str(n) not in stored for n in range(1, len(o.parts) + 1))
            or any(
                not raw.get("statement_id")
                and not _same_evidence(session, workspace_id, o, int(k), raw, judge)
                for k, raw in stored.items()
            )
        )
        if affected:  # every machine-judged part runs again; the visitor's accepted parts stay
            reopened[item_id] = {k: raw for k, raw in stored.items() if raw.get("statement_id")}
    for item_id, keep in reopened.items():
        session.execute(delete(Answer).where(Answer.run_id == run_id, Answer.item_id == item_id))
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id == item_id)
            .values(parts=keep, state="pending", claimed_at=None, attempts=0)
        )
        session.execute(
            update(SuggestedFill)
            .where(
                SuggestedFill.run_id == run_id,
                SuggestedFill.item_id == item_id,
                SuggestedFill.part == 0,
                SuggestedFill.status == "open",
            )
            .values(status="dismissed")
        )
    if reopened:
        # touched now, so it does not read as abandoned before its next step (adversary-1 M5)
        run.status, run.finished_at, run.stepped_at = "running", None, datetime.now(UTC)
        audit_log.record(
            session, workspace_id, "run.recheck", ref=str(run_id), detail={"outcomes": len(reopened)}
        )
    session.commit()
    return len(reopened)

"""Fill runs (spec 6.3): a run lists its items as run_items; each POST /api/runs/{id}/step claims up to
STEP_ITEMS of them in a short transaction (FOR UPDATE SKIP LOCKED), answers them outside any transaction, and
writes one answer row per item (UNIQUE (run_id, item_id): a duplicate write does nothing). No queue, no
worker: the browser drives the loop; a gap-check step claims outcomes by their parts (CSF spec 5.7) and stores
each part as it lands."""

import logging
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

import openai
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import csf
from app.api.errors import ModelsUnavailable, NotFound
from app.classify import PROMPT_VERSION as CLASSIFY_PROMPT
from app.contracts import BudgetExhausted, ItemInput, ItemResult, Spend, jsonable
from app.db.models import Answer, Item, Questionnaire, Run, RunItem, SuggestedFill
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
STEP_PARTS = 8  # CSF spec 5.7: a gap-check step claims outcomes until their parts add up to 8 (8 x 15 s p90)
# An Ask-me outcome waits for the visitor (CSF spec 5.4): no retrieval, no call; gap_label shows Not answered.
ASK: dict[str, Any] = {"label": "unknown", "value": None, "text": "", "confidence": 0.0}


class _OutOfTime(Exception):
    """The step's deadline passed before a part not yet stored (adversary-1 M3): the outcome goes back with
    the parts it stored, and the next step resumes it."""


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
        select(Questionnaire)
        .where(Questionnaire.id == questionnaire_id, Questionnaire.workspace_id == workspace_id)
        .with_for_update(read=True)  # a concurrent mapping change or delete waits, then we see the result
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


def _once[T](session: Session, call: Callable[[], T], can_retry: Callable[[], bool]) -> T:
    """`call`, and once more after a failed model call (a malformed reply rarely repeats). Never again on a
    missing recording or a refused budget, nor once `can_retry` says the step's deadline has passed."""
    try:
        return call()
    except (ReplayMiss, BudgetExhausted):
        raise
    except LLMError as exc:
        if not _retryable(exc) or not can_retry():
            raise
        session.rollback()
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


def _is_current(o: csf.Outcome, n: int, raw: Mapping[str, Any], models: Mapping[str, str]) -> bool:
    """A stored part still stands for part n as deployed: the same wording, judged by the same stance prompt
    and model (adversary-1 M5). A part filled from the visitor's answer has no judge of its own; only its
    wording counts."""
    if not 1 <= n <= len(o.parts) or raw.get("question") != o.parts[n - 1]:
        return False
    judged = (raw.get("stance_prompt"), raw.get("model")) == (STANCE_PROMPT, models["stance"])
    return judged or bool(raw.get("statement_id"))


def _answer_outcome(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    o: csf.Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
    can_retry: Callable[[], bool],
) -> dict[str, Any]:
    """One gap-check outcome (CSF spec 5.2-5.5, 5.7). Ask me: no retrieval and no call. Checked: every part
    not stored yet runs through the pipeline (each retried once, `_once`) and is stored the moment it lands,
    so a step refused by the budget mid-outcome resumes without paying again. A stored part whose wording,
    stance prompt or model differs from the deployed one runs again (`_is_current`). The deadline is checked
    before each part not yet stored (`_OutOfTime`). Then code combines the parts (`outcome_values`)."""
    if o.tier != "checked":
        return dict(ASK)
    have = (
        session.scalar(select(RunItem.parts).where(RunItem.run_id == run_id, RunItem.item_id == item_id))
        or {}
    )
    parts = {
        k: have[k]
        for n in range(1, len(o.parts) + 1)
        if (k := str(n)) in have and _is_current(o, n, have[k], models)
    }
    session.commit()  # no transaction stays open into the first model call
    for n, text in enumerate(o.parts, 1):
        if str(n) in parts:
            continue
        if not can_retry():
            raise _OutOfTime()
        call = partial(csf.check_part, session, workspace_id, o, n, llm, models, spend)
        judged = {"question": text, "stance_prompt": STANCE_PROMPT, "model": models["stance"]}
        parts[str(n)] = _no_nul({**judged, **_raw(_once(session, call, can_retry))})
        session.execute(
            update(RunItem)
            .where(RunItem.run_id == run_id, RunItem.item_id == item_id)
            .values(parts=dict(parts))
        )
        session.commit()
    return outcome_values(o, parts)


def outcome_values(o: csf.Outcome, parts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """A Checked outcome's answer row from its stored parts, all present (CSF spec 5.3): the label by
    `combine`, code's explanation, the parts' citations and drops. Its chunk ids are the parts' union, so a
    metadata override finds it (app.redecide decides it again part by part); no stances of its own. Parts
    filled from the visitor's answer are named "Confirmed by you" in the explanation, and an outcome that
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
    """Answer up to STEP_ITEMS items; returns the item ids answered. Raises BudgetExhausted (a
    `llm_budget.Refused` naming the cap; unstarted items go back to pending) and ReplayMiss (never degraded,
    contract rule). `network` is `errors.network(request)`: the spender counts each call."""
    run = _run(session, workspace_id, run_id)
    if run.status != "running":
        return []
    by_parts = (
        session.scalar(select(Questionnaire.source).where(Questionnaire.id == run.questionnaire_id)) == "csf"
    )
    deadline = clock() + DEADLINE_S
    claimed = _claim(session, run_id, now or datetime.now(UTC), by_parts=by_parts)
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
        try:
            row = session.get_one(Item, item_id)
            # an id a data refresh withdrew is answered as the question it was (adversary-1 N1)
            o = csf.outcome_or_none(row.csf_id) if row.csf_id is not None else None
            if o is not None:
                values = _answer_outcome(
                    session,
                    workspace_id,
                    run_id,
                    item_id,
                    o,
                    meter,
                    models,
                    spend,
                    lambda: clock() <= deadline,
                )
            else:
                item = ItemInput(str(row.id), row.question, row.topic)
                values = _values(
                    _answer(session, workspace_id, item, meter, models, spend, lambda: clock() <= deadline)
                )
        except _OutOfTime:
            _release(session, run_id, rest)  # refunds: the stored parts stay, the outcome was not tried out
            _add_cost(session, run_id, meter.take())
            session.commit()
            break
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
        except LLMError as exc:
            session.rollback()
            if _provider_down(exc):
                # an outage is not a bad answer: the items go back, but the one that met it keeps its
                # attempt, so an item the provider always fails still ends FAILED (adversary-3 N1)
                _release(session, run_id, rest[:1], refund=False)
                _release(session, run_id, rest[1:])
                _add_cost(session, run_id, meter.take())
                session.commit()
                if answered:
                    break  # the next step meets the outage itself
                raise ModelsUnavailable() from None
            if _retryable(exc) and clock() > deadline:
                # the deadline cut the retry: not tried twice, so not failed (Task 8 review)
                _release(session, run_id, rest)
                _add_cost(session, run_id, meter.take())
                session.commit()
                break
            values = FAILED
        except SQLAlchemyError as exc:
            session.rollback()  # triage row 24: a failed transaction must not swallow the next write
            # the type only: the statement's parameters carry the question's words (adversary-3 M1)
            log.error("run %s item %s: %s; answered as failed", run_id, item_id, type(exc).__name__)
            values = FAILED
        except Exception:
            _keep_cost(session, run_id, meter.take(), claimed[n + 1 :])
            raise
        cost = meter.take()
        try:
            try:
                _write(session, workspace_id, run_id, item_id, values, cost)
            except DataError as exc:  # the database refused a value: write the failure, not a reclaim loop
                session.rollback()
                log.error(
                    "run %s item %s: %s on write; answered as failed", run_id, item_id, type(exc).__name__
                )
                _write(session, workspace_id, run_id, item_id, FAILED, cost)
        except Exception:
            _keep_cost(session, run_id, cost, claimed[n + 1 :])
            raise
        answered.append(item_id)
    _finish_if_done(session, run)
    return answered


REOPEN = ("verified", "partial", "conflict", "unknown")  # machine labels; the visitor's own labels stay


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


def reopen_changed(session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int:
    """Check again after an upload (CSF spec 5.6; plan 6B decision 3), with no model call. A Checked outcome
    is affected when a stored part is missing, its wording, judge or evidence changed, or its answer failed.
    Every machine-judged part of an affected outcome is dropped, and the outcome goes back to pending with its
    answer removed and its whole-item fills dismissed, so the step loop runs all of its parts again. A part
    filled by a fill the visitor accepted stays, and so do the open per-part fills (a fill is the visitor's
    answer judged against the part's wording, not the documents), and an outcome the visitor edited,
    approved, confirmed or marked not applicable. Lock order: the run (two presses re-open once), the
    answers by id, then their run items, read under those locks so an accept in flight is waited out and its
    part kept (preflight I1), then the fills. Returns the outcomes re-opened; with any, the run is running."""
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
            Answer.label.in_(REOPEN),
            Answer.edited.is_(False),
            Answer.approved_at.is_(None),
        )
        .order_by(Answer.id)
        .with_for_update(of=Answer)
    ).all()
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
                and not _same_evidence(session, workspace_id, o, int(k), raw, run.models)
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
        run.status, run.finished_at = "running", None
        audit_log.record(
            session, workspace_id, "run.recheck", ref=str(run_id), detail={"outcomes": len(reopened)}
        )
    session.commit()
    return len(reopened)

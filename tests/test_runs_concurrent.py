import contextlib
import json
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import openai
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import csf, runs
from app.api.errors import ModelsUnavailable
from app.contracts import BudgetExhausted
from app.db.models import Answer, Item, LlmUsage, RunItem
from app.llm.client import LLMError, LLMRequest, LLMResult
from app.services import llm_budget
from app.services.llm_budget import spender
from tests import factories as f
from tests.fakes import ByStepLLM

MODELS = {"stance": "m/stance", "draft": "m/draft", "classify": "m/c", "recheck": "m/stance", "judge": "m/j"}
QUOTE = "Customer data at rest is encrypted with AES-256."
STANCE = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
DRAFT = json.dumps({"text": 'Yes. The crypto policy says "Customer data at rest is encrypted with AES-256."'})
LINE = "Backups of data are created, protected, maintained and tested every day."
YES = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": LINE, "note": "states it"}]})
PAUSE = 0.5  # seconds per model call


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


class Slow(ByStepLLM):
    """Every call takes PAUSE seconds and counts the calls in flight at once (adversary-1 M4: assert the
    concurrency, not the speed); a request whose prompt holds `fail` raises `error`."""

    def __init__(
        self, replies: dict[str, str | Exception], fail: str = "", error: Exception | None = None
    ) -> None:
        super().__init__(replies, cost=0.01)
        self.fail, self.error = fail, error
        self.in_flight = self.most = 0

    def complete(self, req: LLMRequest) -> LLMResult:
        with self._lock:
            self.in_flight += 1
            self.most = max(self.most, self.in_flight)
        try:
            time.sleep(PAUSE)
            if self.fail and self.fail in req.user and self.error is not None:
                with self._lock:
                    self.requests.append(req)
                raise self.error
            return super().complete(req)
        finally:
            with self._lock:
                self.in_flight -= 1


def _questionnaire(s: Session, n: int):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="crypto-policy.docx"), line_start=4, line_end=4, text=QUOTE)
    q = f.questionnaire(s, ws)
    for i in range(1, n + 1):
        f.item(
            s,
            q,
            position=i,
            row_ref=f"Q!C{i}",
            code=f"DS-{i:02d}",
            topic="Data Security",
            question=f"Is customer data encrypted at rest? (item {i})",
        )
    s.commit()
    return ws, runs.create_run(s, ws.id, q.id, MODELS)


def _backups(s: Session):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="backup-policy.docx"), line_start=2, line_end=2, text=LINE)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    o = csf.framework().get("PR.DS-11")
    it = f.item(s, q, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question)
    s.commit()
    return ws, it, runs.create_run(s, ws.id, q.id, MODELS)


def _status_error(status: int, headers: dict[str, str] | None = None) -> LLMError:
    err = LLMError(f"stance: {status}")
    response = httpx.Response(status, headers=headers, request=httpx.Request("POST", "http://x"))
    err.__cause__ = openai.APIStatusError("down", response=response, body=None)
    return err


def _outage() -> LLMError:
    return _status_error(503)


def _when_done(monkeypatch: pytest.MonkeyPatch, name: str, jobs: int) -> threading.Event:
    """An event set once `jobs` calls of `runs.<name>` have returned (each has closed its session)."""
    real: Callable[..., Any] = getattr(runs, name)
    finished = threading.Event()
    returned: list[None] = []
    lock = threading.Lock()

    def job(*a: Any, **k: Any) -> Any:
        try:
            return real(*a, **k)
        finally:
            with lock:
                returned.append(None)
                if len(returned) == jobs:
                    finished.set()

    monkeypatch.setattr(runs, name, job)
    return finished


def test_four_items_run_at_once(s: Session) -> None:
    ws, run = _questionnaire(s, 4)
    llm = Slow({"stance": STANCE, "draft": DRAFT})
    answered = runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(answered) == 4 and len(llm.requests) == 8
    assert llm.most >= 2  # calls overlapped (no wall-clock bound: it flakes under load, review I2)
    assert [s.get_one(Item, i).position for i in answered] == [1, 2, 3, 4]  # questionnaire order
    s.refresh(run)
    assert float(run.cost_usd) == pytest.approx(0.08)  # every paid call counted once


def test_a_gap_outcomes_parts_run_at_once(s: Session) -> None:
    ws, it, run = _backups(s)
    llm = Slow({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert llm.most >= 2  # four parts; sequential would be one at a time
    assert sorted(r.item_id for r in llm.requests) == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]
    ri = s.scalars(select(RunItem).where(RunItem.run_id == run.id)).one()
    assert sorted(ri.parts) == ["1", "2", "3", "4"]  # no part lost to a concurrent write
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.value) == ("verified", "Yes")


def test_spending_is_exact_under_concurrency(s: Session, db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    ws = f.workspace(s)
    s.commit()
    ws_id = ws.id  # read once: an expired attribute loaded from 16 threads would share `s`
    allowed: list[bool] = []
    lock = threading.Lock()

    def spend_once() -> None:
        with Session(db) as own:
            ok = spender(own, ws_id, network="net-1")("stance")
        with lock:
            allowed.append(ok)

    threads = [threading.Thread(target=spend_once) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 10  # exactly the cap, never one more
    used = s.scalar(select(LlmUsage.calls).where(LlmUsage.workspace_id == ws_id, LlmUsage.kind == "stance"))
    assert used == 16  # every attempt counted once (a refusal still counts, as before)


def test_a_budget_refusal_mid_step_writes_what_was_paid_and_gives_the_rest_back(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 2)
    ws, run = _questionnaire(s, 4)
    llm = Slow({"stance": STANCE, "draft": DRAFT})
    with pytest.raises(BudgetExhausted) as err:
        runs.step(s, ws.id, run.id, llm, MODELS)
    assert isinstance(err.value, llm_budget.Refused) and err.value.scope == "workspace"
    states = sorted(s.execute(select(RunItem.state, RunItem.attempts)).all())
    assert states == [("done", 1), ("done", 1), ("pending", 0), ("pending", 0)]  # refused: attempt refunded
    assert s.scalar(select(func.count()).select_from(Answer)) == 2
    s.refresh(run)
    assert float(run.cost_usd) == pytest.approx(0.04)  # two items, stance and draft each
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    assert len(runs.step(s, ws.id, run.id, llm, MODELS)) == 2
    assert [r.step for r in llm.requests].count("stance") == 4  # no item's stance was paid twice


def test_an_outage_mid_step_writes_the_others_and_keeps_the_attempt_of_the_item_that_met_it(
    s: Session,
) -> None:
    ws, run = _questionnaire(s, 4)
    llm = Slow({"stance": STANCE, "draft": DRAFT}, fail="(item 3)", error=_outage())
    answered = runs.step(s, ws.id, run.id, llm, MODELS)  # something was answered: no 503
    assert [s.get_one(Item, i).position for i in answered] == [1, 2, 4]
    item3 = s.execute(
        select(RunItem.state, RunItem.attempts)
        .join(Item, Item.id == RunItem.item_id)
        .where(Item.position == 3)
    ).one()
    assert tuple(item3) == ("pending", 1)  # a selective outage: given back, the attempt it met stays counted
    assert s.scalar(select(func.count()).where(Answer.text == runs.FAILED_TEXT)) == 0


def test_an_outage_on_every_item_is_a_503_that_spends_one_attempt(s: Session) -> None:
    # Adversary-1 I3, Ruling 5: a 3-minute outage must not walk a step's items to MAX_ATTEMPTS; only the first
    # item that met it keeps its attempt
    ws, run = _questionnaire(s, 3)
    llm = Slow({"stance": _outage()})
    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, llm, MODELS)
    assert s.scalars(select(Answer)).all() == []
    first = s.execute(
        select(RunItem.state, RunItem.attempts)
        .join(Item, Item.id == RunItem.item_id)
        .where(Item.position == 1)
    ).one()
    assert tuple(first) == ("pending", 1)
    assert sorted(s.execute(select(RunItem.state, RunItem.attempts)).all()) == [
        ("pending", 0),
        ("pending", 0),
        ("pending", 1),
    ]


def _attempts(s: Session) -> dict[int, tuple[str, int]]:
    s.expire_all()
    rows = s.execute(
        select(Item.position, RunItem.state, RunItem.attempts).join(Item, Item.id == RunItem.item_id)
    )
    return {p: (st, at) for p, st, at in rows}


def test_a_sustained_outage_is_a_503_every_step_and_spends_one_attempt_a_step(s: Session) -> None:
    # Review I1: an item written Failed at MAX_ATTEMPTS needed no model call, so it does not make the outage
    # selective; every step is a 503 that keeps at most one attempt, however many items have reached the limit
    ws, run = _questionnaire(s, 5)
    llm = ByStepLLM({"stance": _outage()})
    for _ in range(3 * runs.MAX_ATTEMPTS + 1):
        before = _attempts(s)
        with pytest.raises(ModelsUnavailable):
            runs.step(s, ws.id, run.id, llm, MODELS)
        after = _attempts(s)
        kept = [p for p, (st, at) in after.items() if st == "pending" and at > before[p][1]]
        assert len(kept) <= 1, (before, after)
    states = _attempts(s)
    assert [states[p][0] for p in (1, 2, 3)] == ["done"] * 3  # one item reaches the limit every 3 steps
    assert states[4] == ("pending", 1) and states[5] == ("pending", 0)


def test_an_ask_me_outcome_beside_a_checked_one_does_not_hide_an_outage(s: Session) -> None:
    # Review I1: a gap check's core scope starts with Ask-me outcomes (answered with no call); a Checked one
    # whose every part met the outage still makes the step a 503
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="backup-policy.docx"), line_start=2, line_end=2, text=LINE)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    ask, checked = csf.framework().get("GV.OC-03"), csf.framework().get("PR.DS-11")
    assert (ask.tier, checked.tier) == ("ask", "checked")
    for pos, o in enumerate((ask, checked), 1):
        f.item(
            s, q, position=pos, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question
        )
    s.commit()
    run = runs.create_run(s, ws.id, q.id, MODELS)
    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, ByStepLLM({"stance": _outage()}), MODELS)
    assert _attempts(s) == {1: ("done", 1), 2: ("pending", 1)}
    assert s.scalars(select(Answer.text)).all() == [""]  # the Ask-me row is written; no Failed answer


def test_a_clock_that_raises_in_a_worker_is_settled_not_lost(s: Session) -> None:
    # Review M1: an exception from the clock as a job starts comes back as that job's error; the other job's
    # answer is still written before it is raised
    ws, run = _questionnaire(s, 2)
    reads = iter([0.0, 0.0])  # the deadline, one job's start: the other job's start raises StopIteration

    with pytest.raises(StopIteration):
        runs.step(
            s, ws.id, run.id, ByStepLLM({"stance": STANCE, "draft": DRAFT}), MODELS, clock=lambda: next(reads)
        )
    assert sorted(st for st, _ in _attempts(s).values()) == ["claimed", "done"]  # its attempt stays counted
    assert len(s.scalars(select(Answer)).all()) == 1


def test_items_the_provider_always_fails_end_failed_even_when_they_are_all_that_is_left(s: Session) -> None:
    # Ruling 5: two items that always meet an outage, alone at the end of a run, both end FAILED in a bounded
    # number of steps (a refund for both would 503 forever)
    ws, run = _questionnaire(s, 3)

    class TwoAlwaysFail(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            if "(item 2)" in req.user or "(item 3)" in req.user:
                with self._lock:
                    self.requests.append(req)
                raise _status_error(408)
            return super().complete(req)

    llm = TwoAlwaysFail({"stance": STANCE, "draft": DRAFT})
    for _ in range(2 * runs.MAX_ATTEMPTS + 1):  # 1 + 2 x MAX_ATTEMPTS steps is enough: 6 here, one spare
        with contextlib.suppress(ModelsUnavailable):
            runs.step(s, ws.id, run.id, llm, MODELS)
    s.refresh(run)
    assert run.status == "done"
    texts = dict(s.execute(select(Item.position, Answer.text).join(Answer, Answer.item_id == Item.id)).all())
    assert texts[1] != runs.FAILED_TEXT and texts[2] == texts[3] == runs.FAILED_TEXT


@pytest.mark.parametrize(
    ("headers", "low", "high"),
    [({}, 1.0, 1.5), ({"retry-after": "1.2"}, 1.2, 1.7), ({"retry-after": "30"}, 2.0, 2.0)],
)
def test_a_rate_limit_pauses_before_its_single_retry(
    s: Session, monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], low: float, high: float
) -> None:
    # Adversary-1 I3: eight workers must not re-fire their calls in the same second; with up to 0.5 s of
    # jitter (review M2), never past 2 s
    ws, run = _questionnaire(s, 1)
    slept: list[float] = []
    monkeypatch.setattr(runs.time, "sleep", slept.append)
    llm = ByStepLLM({"stance": _status_error(429, headers)})
    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(llm.requests) == 2 and len(slept) == 1 and low <= slept[0] <= high


def test_a_server_error_is_retried_without_a_pause(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    ws, run = _questionnaire(s, 1)
    slept: list[float] = []
    monkeypatch.setattr(runs.time, "sleep", slept.append)
    llm = ByStepLLM({"stance": _outage()})
    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, llm, MODELS)
    assert (len(llm.requests), slept) == (2, [])


def test_a_step_returns_by_its_hard_limit_and_keeps_the_slow_items_attempt(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runs, "HARD_S", 0.5)
    finished = _when_done(monkeypatch, "_item_job", 1)
    ws, run = _questionnaire(s, 1)
    release = threading.Event()

    class Stuck(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            release.wait(10)  # a provider that does not answer inside the step
            raise _status_error(400)  # not retried: the abandoned worker makes no second call (preflight M6)

    start = time.monotonic()
    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, Stuck({}), MODELS)
    assert (
        time.monotonic() - start < 5.0
    )  # far below the provider's 10 s; Vercel would have killed it at 300 s
    assert tuple(s.execute(select(RunItem.state, RunItem.attempts)).one()) == ("pending", 1)  # late: kept
    assert s.scalars(select(Answer)).all() == []
    release.set()
    assert finished.wait(10)  # the abandoned worker has closed its session before the next test truncates
    assert s.scalars(select(Answer)).all() == []  # and wrote nothing


def test_a_late_part_lands_on_no_row_once_its_outcome_was_released(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Adversary-1 M1: the part write is guarded by this claim, so a part that lands after the step answered
    # (and after a Check again or a reclaim) never comes back with older evidence
    monkeypatch.setattr(runs, "HARD_S", 2.0)  # parts 1-3 land well inside it
    finished = _when_done(monkeypatch, "_part_job", 4)
    ws, it, run = _backups(s)
    release = threading.Event()

    class FourthIsStuck(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            if req.item_id.endswith("#4"):
                release.wait(10)
            return super().complete(req)

    with pytest.raises(ModelsUnavailable):
        runs.step(s, ws.id, run.id, FourthIsStuck({"stance": YES}), MODELS)
    release.set()
    assert finished.wait(10)
    s.expire_all()
    ri = s.scalars(select(RunItem).where(RunItem.run_id == run.id)).one()
    assert (ri.state, ri.attempts) == ("pending", 1)
    assert sorted(ri.parts) == ["1", "2", "3"]  # part 4 landed after the release: no row took it


def test_a_retry_spent_in_time_is_a_failed_answer_even_when_settled_after_the_deadline(s: Session) -> None:
    # Adversary-1 M2: tried twice before the deadline means failed, however slow the neighbours were
    ws, run = _questionnaire(s, 1)
    llm = ByStepLLM({"stance": "not json"})
    ticks = iter([0.0, 0.0, 0.0])  # the deadline, the job's start, its retry: then every read is late
    assert len(runs.step(s, ws.id, run.id, llm, MODELS, clock=lambda: next(ticks, 1e9))) == 1
    assert len(llm.requests) == 2
    assert s.scalars(select(Answer.text)).one() == runs.FAILED_TEXT


def test_a_failed_write_leaves_its_item_claimed_and_still_writes_the_others(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Adversary-1 M3: the others were paid; their answers are written, not given back to be paid again
    ws, run = _questionnaire(s, 3)
    first = s.scalar(select(Item.id).where(Item.position == 1))
    real = runs._write

    def write(session, workspace_id, run_id, item_id, values, cost):  # type: ignore[no-untyped-def]
        if item_id == first:
            raise RuntimeError("the write failed")
        return real(session, workspace_id, run_id, item_id, values, cost)

    monkeypatch.setattr(runs, "_write", write)
    llm = ByStepLLM({"stance": STANCE, "draft": DRAFT}, cost=0.01)
    with pytest.raises(RuntimeError, match="the write failed"):
        runs.step(s, ws.id, run.id, llm, MODELS)
    by_pos = dict(
        s.execute(select(Item.position, RunItem.state).join(Item, Item.id == RunItem.item_id)).all()
    )
    assert by_pos == {1: "claimed", 2: "done", 3: "done"}
    s.refresh(run)
    assert float(run.cost_usd) == pytest.approx(0.06)  # the failed item's calls still count


def test_an_error_before_any_job_starts_gives_every_other_item_back(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Preflight M4: items listed before the one that failed were not started either
    ws, run = _questionnaire(s, 3)
    second = s.scalar(select(Item.id).where(Item.position == 2))
    real = Session.get_one

    def boom(self, entity, ident, *a, **k):  # type: ignore[no-untyped-def]
        if entity is runs.Item and ident == second:
            raise RuntimeError("lost the item")
        return real(self, entity, ident, *a, **k)

    monkeypatch.setattr(Session, "get_one", boom)
    with pytest.raises(RuntimeError):
        runs.step(s, ws.id, run.id, ByStepLLM({}), MODELS)
    rows = s.execute(
        select(Item.position, RunItem.state, RunItem.attempts).join(Item, Item.id == RunItem.item_id)
    )
    by_pos = {p: (st, at) for p, st, at in rows}
    assert by_pos == {1: ("pending", 0), 2: ("claimed", 1), 3: ("pending", 0)}


def test_no_worker_holds_a_transaction_while_it_calls_a_model(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, run = _questionnaire(s, 4)
    mine = threading.local()
    real = runs._session

    def watched(engine: Engine) -> Session:
        mine.session = real(engine)
        return mine.session

    monkeypatch.setattr(runs, "_session", watched)

    class Watching(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not mine.session.in_transaction(), f"{req.step} ran inside its worker's open transaction"
            assert not s.in_transaction(), "the request's session held a transaction during a call"
            return super().complete(req)

    llm = Watching({"stance": STANCE, "draft": DRAFT})
    assert len(runs.step(s, ws.id, run.id, llm, MODELS)) == 4
    assert len(llm.requests) == 8

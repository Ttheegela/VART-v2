import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app import runs
from app.api.errors import NotFound
from app.contracts import BudgetExhausted
from app.db.models import Answer, LlmUsage, Run, RunItem
from app.llm.client import LLMError, LLMRequest, LLMResult
from app.llm.recorder import ReplayMiss
from app.services import llm_budget
from app.services.ip_limits import LIMITS, hit
from tests import factories as f
from tests.fakes import ByStepLLM

MODELS = {"stance": "m/stance", "draft": "m/draft", "classify": "m/c", "recheck": "m/stance", "judge": "m/j"}
QUOTE = "Customer data at rest is encrypted with AES-256."
STANCE = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
DRAFT = json.dumps({"text": 'Yes. The crypto policy says "Customer data at rest is encrypted with AES-256."'})


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _questionnaire(s: Session, n: int = 6):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    d = f.document(s, ws, filename="crypto-policy.docx")
    f.chunk(s, d, line_start=4, line_end=4, text=QUOTE)
    q = f.questionnaire(s, ws)
    for i in range(1, n + 1):
        f.item(
            s,
            q,
            position=i,
            row_ref=f"Q!C{i + 5}",
            code=f"DS-{i:02d}",
            question="Is customer data encrypted at rest?",
            topic="Data Security",
        )
    s.commit()
    return ws, q


def _llm(**kw):  # type: ignore[no-untyped-def]
    return ByStepLLM({"stance": STANCE, "draft": DRAFT}, **kw)


def test_a_run_is_created_with_every_item_pending(s: Session) -> None:
    ws, q = _questionnaire(s)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    states = s.scalars(select(RunItem.state).where(RunItem.run_id == run.id)).all()
    assert states == ["pending"] * 6
    assert run.prompt_versions == {"stance": "stance@p3", "draft": "draft@p2", "classify": "classify@p1"}
    assert run.models == MODELS


def test_a_step_answers_at_most_four_items_and_the_run_finishes(s: Session) -> None:
    ws, q = _questionnaire(s)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    assert len(runs.step(s, ws.id, run.id, _llm(), MODELS)) == 4
    assert len(runs.step(s, ws.id, run.id, _llm(), MODELS)) == 2
    s.refresh(run)
    assert run.status == "done" and run.finished_at is not None
    assert runs.step(s, ws.id, run.id, _llm(), MODELS) == []
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).first()
    assert a is not None and a.label == "verified" and a.chunk_ids and a.stances[0]["stance"] == "yes"


def test_a_repeated_step_is_a_no_op_for_finished_items(s: Session) -> None:
    ws, q = _questionnaire(s, n=2)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    llm = _llm(cost=0.01)
    runs.step(s, ws.id, run.id, llm, MODELS)
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(llm.requests) == 4  # two items, stance and draft each, once
    assert s.scalar(select(func.count()).select_from(Answer)) == 2
    s.refresh(run)
    assert run.cost_usd == Decimal("0.0400")  # charged once


def test_two_steps_at_once_never_process_an_item_twice(db: Engine) -> None:
    with Session(db) as s:
        ws, q = _questionnaire(s, n=8)
        run = runs.create_run(s, ws.id, q.id, MODELS)
        ws_id, run_id = ws.id, run.id
    llm = _llm(cost=0.01)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with Session(db) as own:
                barrier.wait()
                runs.step(own, ws_id, run_id, llm, MODELS)
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    keys = [r.item_id for r in llm.requests if r.step == "stance"]
    assert len(keys) == len(set(keys)) == 8
    with Session(db) as s:
        assert s.scalar(select(func.sum(LlmUsage.calls)).where(LlmUsage.kind == "stance")) == 8
        assert s.scalar(select(func.count()).select_from(Answer)) == 8
        done = s.get_one(Run, run_id)
        assert done.status == "done" and done.cost_usd == Decimal("0.1600")


def test_no_transaction_is_open_while_a_model_runs(s: Session) -> None:
    ws, q = _questionnaire(s, n=2)
    run = runs.create_run(s, ws.id, q.id, MODELS)

    class Watching(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not s.in_transaction(), f"{req.step} ran inside an open transaction"
            return super().complete(req)

    llm = Watching({"stance": STANCE, "draft": DRAFT})
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(llm.requests) == 4


def test_no_transaction_is_open_during_a_retry_either(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    replies = iter(["[]", STANCE])

    class Watching(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not s.in_transaction(), f"{req.step} ran inside an open transaction"
            if req.step == "stance":
                self.requests.append(req)
                return LLMResult(next(replies), 10, 5, 0.0)
            return super().complete(req)

    llm = Watching({"draft": DRAFT})
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert [r.step for r in llm.requests] == ["stance", "stance", "draft"]
    assert s.scalars(select(Answer.label)).one() == "verified"


def test_a_malformed_reply_is_retried_once_and_its_cost_still_counts(s: Session) -> None:
    # Triage rows 16 and 51: DeepSeek returned a JSON array about once in 350 calls; the paid call's cost was
    # lost when answer_item raised.
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    replies = iter(["[]", STANCE])

    class Flaky(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            if req.step == "stance":
                self.requests.append(req)
                return LLMResult(next(replies), 10, 5, 0.01)
            return super().complete(req)

    runs.step(s, ws.id, run.id, Flaky({"draft": DRAFT}, cost=0.01), MODELS)
    s.refresh(run)
    a = s.scalars(select(Answer)).one()
    assert a.label == "verified"
    assert run.cost_usd == Decimal("0.0300")  # two stance calls and one draft call


def test_two_failures_leave_an_unknown_answer_that_says_so(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": LLMError("stance: timeout")}), MODELS)
    a = s.scalars(select(Answer)).one()
    assert (a.label, a.text) == ("unknown", runs.FAILED_TEXT)
    s.refresh(run)
    assert run.status == "done"


def test_a_missing_recording_is_never_swallowed(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    with pytest.raises(ReplayMiss):
        runs.step(s, ws.id, run.id, ByStepLLM({"stance": ReplayMiss("stance: no recording")}), MODELS)
    assert s.scalars(select(RunItem.state)).one() == "pending"  # returned, not lost


def test_a_refused_budget_returns_the_unstarted_items(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    ws, q = _questionnaire(s, n=4)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    with pytest.raises(BudgetExhausted) as err:
        runs.step(s, ws.id, run.id, _llm(), MODELS)
    assert isinstance(err.value, llm_budget.Refused) and err.value.scope == "workspace"
    states = sorted(s.scalars(select(RunItem.state).where(RunItem.run_id == run.id)))
    assert states == ["done", "pending", "pending", "pending"]


def test_the_network_limit_counts_per_model_call_and_names_its_scope(s: Session) -> None:
    ws, q = _questionnaire(s, n=4)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    for _ in range(LIMITS["llm"][0] - 1):  # one call left for this network
        hit(s, "net-1", "llm")
    s.commit()
    with pytest.raises(llm_budget.Refused) as err:
        runs.step(s, ws.id, run.id, _llm(), MODELS, network="net-1")
    assert err.value.scope == "network"
    # item 1 took the last stance call (its draft fell back to the template); item 2 was refused
    assert sorted(s.scalars(select(RunItem.state))) == ["done", "pending", "pending", "pending"]


def test_a_database_error_is_rolled_back_before_the_failure_is_written(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Triage row 24: a DB error inside answer_item left the session in a failed transaction, so the runner's
    # next write raised "current transaction is aborted".
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)

    def broken(session, *a, **kw):  # type: ignore[no-untyped-def]
        session.execute(text("select 1/0"))

    monkeypatch.setattr(runs, "answer_item", broken)
    runs.step(s, ws.id, run.id, _llm(), MODELS)
    a = s.scalars(select(Answer)).one()
    assert (a.label, a.text) == ("unknown", runs.FAILED_TEXT)


def test_a_stale_claim_is_taken_again(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    s.execute(
        RunItem.__table__.update().values(
            state="claimed", claimed_at=datetime.now(UTC) - timedelta(minutes=6)
        )
    )
    s.commit()
    assert len(runs.step(s, ws.id, run.id, _llm(), MODELS)) == 1


def test_a_fresh_claim_is_left_alone(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    s.execute(RunItem.__table__.update().values(state="claimed", claimed_at=datetime.now(UTC)))
    s.commit()
    llm = _llm()
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [] and llm.requests == []


def test_an_item_that_crashed_three_times_is_answered_as_failed(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    s.execute(RunItem.__table__.update().values(attempts=runs.MAX_ATTEMPTS))
    s.commit()
    llm = _llm()
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert llm.requests == [] and s.scalars(select(Answer.text)).one() == runs.FAILED_TEXT


def test_the_deadline_returns_the_rest(s: Session) -> None:
    ws, q = _questionnaire(s, n=4)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    ticks = iter([0.0, 0.0, runs.DEADLINE_S + 1, runs.DEADLINE_S + 1, runs.DEADLINE_S + 1])
    done = runs.step(s, ws.id, run.id, _llm(), MODELS, clock=lambda: next(ticks))
    assert len(done) == 1
    assert sorted(s.scalars(select(RunItem.state))) == ["done", "pending", "pending", "pending"]


def test_another_workspaces_run_is_not_found(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    other = f.workspace(s)
    s.commit()
    with pytest.raises(NotFound):
        runs.step(s, other.id, run.id, _llm(), MODELS)


def _attempts(s: Session) -> list[int]:
    s.expire_all()
    return list(s.scalars(select(RunItem.attempts)))


def test_refused_steps_do_not_burn_attempts(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # Review C1: a released claim used to keep its attempt, so 3 refusals condemned the items untried.
    ws, q = _questionnaire(s, n=4)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    monkeypatch.setitem(llm_budget.CAPS, "stance", 0)
    for _ in range(runs.MAX_ATTEMPTS + 1):
        with pytest.raises(BudgetExhausted):
            runs.step(s, ws.id, run.id, _llm(), MODELS)
    assert _attempts(s) == [0, 0, 0, 0]
    monkeypatch.setitem(llm_budget.CAPS, "stance", 150)
    llm = _llm()
    assert len(runs.step(s, ws.id, run.id, llm, MODELS)) == 4
    assert len(llm.requests) == 8 and set(s.scalars(select(Answer.label))) == {"verified"}


def test_deadline_releases_do_not_burn_attempts(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    for _ in range(runs.MAX_ATTEMPTS + 1):
        ticks = iter([0.0, runs.DEADLINE_S + 1])
        assert runs.step(s, ws.id, run.id, _llm(), MODELS, clock=ticks.__next__) == []
    assert _attempts(s) == [0]
    assert s.scalars(select(RunItem.state)).one() == "pending"
    llm = _llm()
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(llm.requests) == 2 and s.scalars(select(Answer.label)).one() == "verified"


def test_the_cost_of_a_missing_recording_is_still_written(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    replies = iter([STANCE])

    class Miss(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            if req.step == "stance":
                return LLMResult(next(replies), 10, 5, 0.02)
            raise ReplayMiss("draft: no recording")

    with pytest.raises(ReplayMiss):
        runs.step(s, ws.id, run.id, Miss({}), MODELS)
    s.refresh(run)
    assert run.cost_usd == Decimal("0.0200")


def test_the_cost_of_a_refused_step_is_still_written(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    ws, q = _questionnaire(s, n=2)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    with pytest.raises(BudgetExhausted):
        runs.step(s, ws.id, run.id, _llm(cost=0.01), MODELS)
    s.refresh(run)
    assert run.cost_usd == Decimal("0.0200")  # item 1: stance and draft; item 2 refused


class _Status(Exception):
    status_code = 401


def test_a_client_error_is_not_retried(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    err = LLMError("stance: AuthenticationError")
    err.__cause__ = _Status()
    llm = ByStepLLM({"stance": err})
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(llm.requests) == 1 and s.scalars(select(Answer.text)).one() == runs.FAILED_TEXT


def test_a_server_error_is_retried(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    err = LLMError("stance: InternalServerError")
    cause = _Status()
    cause.status_code = 503
    err.__cause__ = cause
    llm = ByStepLLM({"stance": err})
    runs.step(s, ws.id, run.id, llm, MODELS)
    assert len(llm.requests) == 2


def test_an_unexpected_error_keeps_the_cost_already_spent(s: Session) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)

    class Boom(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            if req.step == "draft":
                raise RuntimeError("boom")
            return LLMResult(STANCE, 10, 5, 0.02)

    with pytest.raises(RuntimeError):
        runs.step(s, ws.id, run.id, Boom({}), MODELS)
    s.refresh(run)
    assert run.cost_usd == Decimal("0.0200")
    assert s.scalars(select(RunItem.state)).one() == "claimed"  # its attempt stays counted


def test_a_failed_answer_write_keeps_the_cost_already_spent(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, q = _questionnaire(s, n=1)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    real = runs._write

    def bad(session, ws_id, run_id, item_id, values, cost):  # type: ignore[no-untyped-def]
        session.execute(text("select 1/0"))

    monkeypatch.setattr(runs, "_write", bad)
    with pytest.raises(Exception, match="division by zero"):
        runs.step(s, ws.id, run.id, _llm(cost=0.01), MODELS)
    monkeypatch.setattr(runs, "_write", real)
    s.refresh(run)
    assert run.cost_usd == Decimal("0.0200")

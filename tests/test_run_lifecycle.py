import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select, text, update
from sqlalchemy.orm import Session

from app import runs
from app.api.errors import Conflict
from app.contracts import BudgetExhausted
from app.db.models import Run, RunItem, Workspace
from app.services import llm_budget
from tests import factories as f
from tests.apiclient import visitor
from tests.fakes import ByStepLLM
from tests.test_runs import STANCE
from tests.test_runs_csf import _done
from tests.test_sample_run import _sample

MODELS = {"stance": "m/stance", "draft": "m/draft", "classify": "m/c", "recheck": "m/stance", "judge": "m/j"}
IDLE = timedelta(minutes=11)
BEFORE = "c4e8a2d6f1b3"


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _questionnaire(s: Session, ws: Workspace | None = None, n: int = 1):  # type: ignore[no-untyped-def]
    ws = ws or f.workspace(s)
    q = f.questionnaire(s, ws)
    for i in range(1, n + 1):
        f.item(s, q, position=i, row_ref=f"Q!C{i}", code=f"X-{i:02d}", question=f"Is data encrypted? ({i})")
    s.commit()
    return ws, q


def _idle(s: Session, run: Run) -> None:
    s.execute(
        update(Run).where(Run.id == run.id).values(started_at=datetime.now(UTC) - IDLE, stepped_at=None)
    )
    s.commit()


def _lock_waiters(db: Engine) -> int:
    with db.connect() as conn:
        return int(conn.scalar(text("select count(*) from pg_locks where not granted")) or 0)


def _pause_first_abandoned_record(monkeypatch: pytest.MonkeyPatch) -> tuple[threading.Event, threading.Event]:
    """The first `run.abandoned` audit record waits (its run row is locked by then) until `go_on` is set."""
    inside, go_on = threading.Event(), threading.Event()
    real = runs.audit_log.record

    def slow(session: Session, ws_id: uuid.UUID, action: str, **kw: Any) -> None:
        if action == "run.abandoned" and not inside.is_set():
            inside.set()
            go_on.wait(10)
        real(session, ws_id, action, **kw)

    monkeypatch.setattr(runs.audit_log, "record", slow)
    return inside, go_on


def _until_someone_waits(db: Engine) -> bool:
    for _ in range(100):
        if _lock_waiters(db):
            return True
        time.sleep(0.05)
    return False


def test_a_second_run_while_one_is_going_is_refused(s: Session) -> None:
    ws, q = _questionnaire(s)
    runs.create_run(s, ws.id, q.id, MODELS)
    with pytest.raises(Conflict):
        runs.create_run(s, ws.id, q.id, MODELS)
    s.rollback()
    assert s.scalar(select(func.count()).select_from(Run)) == 1


def test_a_run_of_another_questionnaire_is_not_in_the_way(s: Session) -> None:
    ws, q = _questionnaire(s)
    _, other = _questionnaire(s, ws)
    runs.create_run(s, ws.id, q.id, MODELS)
    assert runs.create_run(s, ws.id, other.id, MODELS).status == "running"


def test_an_abandoned_run_is_closed_and_a_new_one_starts(s: Session) -> None:
    ws, q = _questionnaire(s)
    old = runs.create_run(s, ws.id, q.id, MODELS)
    _idle(s, old)
    new = runs.create_run(s, ws.id, q.id, MODELS)
    s.refresh(old)
    assert (old.status, new.status) == ("failed", "running") and old.finished_at is not None


def test_a_step_keeps_its_run_from_reading_as_abandoned(s: Session) -> None:
    ws, q = _questionnaire(s, n=6)  # no documents: every item is unknown with no model call
    run = runs.create_run(s, ws.id, q.id, MODELS)
    _idle(s, run)
    assert len(runs.step(s, ws.id, run.id, ByStepLLM({}), MODELS)) == 4
    s.refresh(run)
    assert run.stepped_at is not None and run.stepped_at > datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(Conflict):
        runs.create_run(s, ws.id, q.id, MODELS)


def test_a_step_never_writes_into_a_run_closed_since_it_read_it(
    s: Session, db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # adversary-1 I2: a close between the step's read and its stepped_at update leaves the run alone
    ws, q = _questionnaire(s, n=2)
    run = runs.create_run(s, ws.id, q.id, MODELS)
    _idle(s, run)
    real = runs._run

    def read_then_closed(session: Session, ws_id: uuid.UUID, run_id: uuid.UUID) -> Run:
        found = real(session, ws_id, run_id)
        with Session(db) as other:
            assert runs.close_abandoned(other, ws_id) == 1
            other.commit()
        return found

    monkeypatch.setattr(runs, "_run", read_then_closed)
    llm = ByStepLLM({})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == []
    rows = s.execute(select(RunItem.state, RunItem.attempts).where(RunItem.run_id == run.id)).all()
    assert sorted(rows) == [("pending", 0), ("pending", 0)] and llm.requests == []
    s.refresh(run)
    assert (run.status, run.stepped_at) == ("failed", None)


def test_a_run_waiting_on_a_budget_429_never_reads_as_abandoned(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # preflight I5: the step loop waits Retry-After (up to an hour) with no step; the run reads as touched
    monkeypatch.setitem(llm_budget.CAPS, "stance", 0)
    monkeypatch.setattr(runs, "retry_after_budget", lambda **_: 3600)
    ws = f.workspace(s)
    d = f.document(s, ws, filename="crypto-policy.docx")
    f.chunk(s, d, text="Customer data at rest is encrypted with AES-256.")
    q = f.questionnaire(s, ws)
    f.item(
        s,
        q,
        position=1,
        row_ref="Q!C1",
        question="Is customer data encrypted at rest?",
        topic="Data Security",
    )
    s.commit()
    run = runs.create_run(s, ws.id, q.id, MODELS)
    _idle(s, run)
    with pytest.raises(BudgetExhausted):
        runs.step(s, ws.id, run.id, ByStepLLM({"stance": STANCE}), MODELS)
    s.refresh(run)
    assert run.stepped_at is not None and run.stepped_at > datetime.now(UTC) + timedelta(minutes=50)
    with pytest.raises(Conflict):
        runs.create_run(s, ws.id, q.id, MODELS)


def test_check_again_touches_the_run_it_reopens(s: Session) -> None:
    # adversary-1 M5: a re-opened run whose last step is old must not read as abandoned before its next step
    ws, _, run = _done(s)
    s.execute(update(RunItem).where(RunItem.run_id == run.id).values(parts={}))  # every part missing
    s.commit()
    _idle(s, run)
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    assert runs.close_abandoned(s, ws.id) == 0
    s.refresh(run)
    assert run.status == "running" and run.stepped_at is not None


def test_two_new_runs_at_once_make_one(db: Engine) -> None:
    with Session(db) as s:
        ws, q = _questionnaire(s)
        ws_id, q_id = ws.id, q.id
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def go() -> None:
        with Session(db) as own:
            barrier.wait()
            try:
                runs.create_run(own, ws_id, q_id, MODELS)
                outcomes.append("ok")
            except Conflict:
                outcomes.append("conflict")

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["conflict", "ok"]


def test_a_new_run_and_a_document_delete_at_once_never_deadlock(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # adversary-1 I1: the create holds the questionnaire and the abandoned run, then its insert wants the
    # workspace row; the delete must not hold that row while it waits for the run. Two guards each prevent
    # this (task-4 review m1): close_abandoned takes the workspace KEY SHARE before any run row, and
    # delete_document closes and commits before its workspace lock. The test pins the pair: it fails only with
    # both reverted.
    client, ws_id = visitor(db)
    with Session(db) as s:
        ws = s.get_one(Workspace, ws_id)
        doc = f.document(s, ws, filename="notes.md")
        _, q = _questionnaire(s, ws)
        old = runs.create_run(s, ws_id, q.id, MODELS)
        _idle(s, old)
        doc_id, q_id, old_id = doc.id, q.id, old.id
    inside, go_on = _pause_first_abandoned_record(monkeypatch)
    errors: list[BaseException] = []
    deleted: list[int] = []

    def create() -> None:
        with Session(db) as t:
            try:
                runs.create_run(t, ws_id, q_id, MODELS)
            except BaseException as exc:
                errors.append(exc)

    def delete_doc() -> None:
        try:
            deleted.append(client.delete(f"/api/documents/{doc_id}").status_code)
        except BaseException as exc:
            errors.append(exc)

    a = threading.Thread(target=create)
    a.start()
    assert inside.wait(10)
    b = threading.Thread(target=delete_doc)
    b.start()
    waited = _until_someone_waits(db)
    go_on.set()
    a.join(20)
    b.join(20)
    assert waited and errors == []
    assert deleted == [409]  # the new run is going: the delete is refused, not a 500
    with Session(db) as s:
        assert s.get_one(Run, old_id).status == "failed"


def test_closing_abandoned_runs_and_a_workspace_reset_at_once_never_deadlock(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # close_abandoned takes the workspace row (FOR KEY SHARE) before any run row, so a reset (which holds the
    # workspace row and cascades to the runs) waits for it or goes first, never both at once.
    with Session(db) as s:
        ws, q = _questionnaire(s)
        run = runs.create_run(s, ws.id, q.id, MODELS)
        _idle(s, run)
        ws_id = ws.id
    inside, go_on = _pause_first_abandoned_record(monkeypatch)
    errors: list[BaseException] = []

    def close() -> None:
        with Session(db) as t:
            try:
                runs.close_abandoned(t, ws_id)
                t.commit()
            except BaseException as exc:
                errors.append(exc)

    def reset() -> None:
        with Session(db) as t:
            try:
                t.execute(delete(Workspace).where(Workspace.id == ws_id))
                t.commit()
            except BaseException as exc:
                errors.append(exc)

    a = threading.Thread(target=close)
    a.start()
    assert inside.wait(10)
    b = threading.Thread(target=reset)
    b.start()
    waited = _until_someone_waits(db)
    go_on.set()
    a.join(20)
    b.join(20)
    assert waited and errors == []
    with Session(db) as s:
        assert s.get(Workspace, ws_id) is None


def test_a_copied_sample_run_is_never_refused_while_a_live_run_is_going(db: Engine) -> None:
    # task-4 review m4: the copy spends nothing, so the 409 is for live runs only
    client, _ = visitor(db)
    q_id = _sample(client)["q"]["id"]
    live = client.post(f"/api/questionnaires/{q_id}/runs", params={"live": "true"})
    assert (live.status_code, live.json()["status"]) == (201, "running")
    copy = client.post(f"/api/questionnaires/{q_id}/runs")
    assert (copy.status_code, copy.json()["precomputed"]) == (201, True)
    again = client.post(f"/api/questionnaires/{q_id}/runs", params={"live": "true"})
    assert (again.status_code, again.json()["detail"]) == (409, runs.RUN_IN_PROGRESS)


def test_the_runs_endpoint_answers_409_with_a_sentence(db: Engine) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        _, q = _questionnaire(s, s.get_one(Workspace, ws_id))
        q_id = q.id
    assert client.post(f"/api/questionnaires/{q_id}/runs").status_code == 201
    second = client.post(f"/api/questionnaires/{q_id}/runs")
    assert second.status_code == 409 and second.json()["detail"] == runs.RUN_IN_PROGRESS


def test_an_abandoned_run_no_longer_blocks_a_document_delete(db: Engine) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        ws = s.get_one(Workspace, ws_id)
        doc = f.document(s, ws, filename="notes.md")
        _, q = _questionnaire(s, ws)
        run = runs.create_run(s, ws_id, q.id, MODELS)
        _idle(s, run)
        doc_id, run_id = doc.id, run.id
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    with Session(db) as s:
        assert s.get_one(Run, run_id).status == "failed"


def test_the_gap_check_starts_again_after_a_failed_run(db: Engine) -> None:
    client, _ = visitor(db)
    first = client.post("/api/gap/core/run").json()  # no documents: a live run, not a copy
    with Session(db) as s:
        s.execute(update(Run).where(Run.id == uuid.UUID(first["id"])).values(status="failed"))
        s.commit()
    second = client.post("/api/gap/core/run").json()
    assert second["id"] != first["id"] and second["status"] == "running"


def test_the_stepped_at_migration_runs_down_and_up(db: Engine) -> None:
    cfg = Config("alembic.ini")
    try:
        command.downgrade(cfg, BEFORE)
        with db.connect() as conn:
            found = conn.execute(
                text(
                    "select 1 from information_schema.columns "
                    "where table_name = 'runs' and column_name = 'stepped_at'"
                )
            ).all()
            assert found == []
    finally:
        command.upgrade(cfg, "head")

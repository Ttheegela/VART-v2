import json
import threading
import uuid
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.api.answers import WHY
from app.api.deps import get_llm
from app.api.schemas import DroppedOut
from app.contracts import DropReason
from app.db.models import Answer, AuditEvent, DocumentLine, Workspace
from app.main import app
from app.services import ip_limits
from tests import factories as f
from tests.apiclient import visitor
from tests.fakes import ByStepLLM

QUOTE = "Customer data at rest is encrypted with AES-256."
STANCE = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
DRAFT = json.dumps({"text": 'Yes. The crypto policy says "Customer data at rest is encrypted with AES-256."'})


@pytest.fixture
def ready(db: Engine):  # type: ignore[no-untyped-def]
    client, ws_id = visitor(db)
    with Session(db) as s:
        ws = s.get_one(Workspace, ws_id)
        d = f.document(s, ws, filename="crypto-policy.docx")
        for n in range(1, 4):
            f.chunk(s, d, line_start=n, line_end=n, text=QUOTE if n == 2 else f"Heading {n}")
        s.execute(
            DocumentLine.__table__.insert(),
            [{"document_id": d.id, "n": n, "text": QUOTE if n == 2 else f"Heading {n}"} for n in range(1, 4)],
        )
        q = f.questionnaire(s, ws)
        f.item(s, q, question="Is customer data encrypted at rest?", topic="Data Security", code="DS-01")
        s.commit()
        qid = q.id
    app.dependency_overrides[get_llm] = lambda: ByStepLLM({"stance": STANCE, "draft": DRAFT})
    yield client, qid
    app.dependency_overrides.clear()


def _run_to_end(client: TestClient, qid) -> dict:  # type: ignore[no-untyped-def]
    run = client.post(f"/api/questionnaires/{qid}/runs").json()
    while run["status"] == "running":
        r = client.post(f"/api/runs/{run['id']}/step")
        assert r.status_code == 200, r.text
        run = r.json()["run"]
    return run


def _answer_id(client: TestClient, run: dict) -> str:
    return client.get(f"/api/runs/{run['id']}/answers").json()["rows"][0]["answer"]["id"]


def test_a_run_fills_through_the_step_loop(ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    rows = client.get(f"/api/runs/{run['id']}/answers").json()["rows"]
    assert [(r["item"]["code"], r["answer"]["label"]) for r in rows] == [("DS-01", "verified")]
    assert rows[0]["answer"]["approved"] is False and rows[0]["answer"]["sources"] == 1
    assert client.get(f"/api/runs/{run['id']}").json()["done"] == 1


def test_a_step_on_a_finished_run_answers_nothing(ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    body = client.post(f"/api/runs/{run['id']}/step").json()
    assert body["answered"] == [] and body["run"]["status"] == "done"


def test_the_drawer_rereads_each_citation_with_context(ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    d = client.get(f"/api/answers/{_answer_id(client, run)}").json()
    c = d["citations"][0]
    assert c["found_in_source"] is True and c["line"] == 2
    assert [(x["n"], x["cited"]) for x in c["context"]] == [(1, False), (2, True), (3, False)]


def test_approve_rules_and_bulk_approve(ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    assert client.post(f"/api/runs/{run['id']}/approve-verified").json() == {
        "approved": 1,
        "skipped_edited": 0,
    }
    answer_id = _answer_id(client, run)
    edited = client.patch(f"/api/answers/{answer_id}", json={"text": "Yes, AES-256."}).json()
    assert (edited["edited"], edited["approved"]) == (True, False)
    na = client.post(
        f"/api/answers/{answer_id}/not-applicable", json={"reason": "We take no card data."}
    ).json()
    assert (na["label"], na["text"]) == ("na", "Not applicable: We take no card data.")


def test_bulk_approve_leaves_an_edited_answer_for_a_look(ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    client.patch(f"/api/answers/{_answer_id(client, run)}", json={"text": "Yes, but changed."})
    assert client.post(f"/api/runs/{run['id']}/approve-verified").json() == {
        "approved": 0,
        "skipped_edited": 1,
    }
    assert client.post(f"/api/answers/{_answer_id(client, run)}/approve").json()["approved"] is True


def test_an_approval_waits_for_a_writer_and_then_sees_its_result(db: Engine, ready) -> None:  # type: ignore[no-untyped-def]
    # Task 8 review: edit, approve and not-applicable take turns on the answer row (FOR UPDATE). Without
    # the lock the approval reads the old label and approves what became a conflict.
    client, qid = ready
    answer_id = _answer_id(client, _run_to_end(client, qid))
    result: list[int] = []

    def approve() -> None:
        result.append(client.post(f"/api/answers/{answer_id}/approve").status_code)

    with Session(db) as holder:
        holder.execute(select(Answer).where(Answer.id == answer_id).with_for_update()).one()
        t = threading.Thread(target=approve)
        t.start()
        t.join(0.7)
        assert t.is_alive()  # waiting for the lock
        holder.execute(update(Answer).where(Answer.id == answer_id).values(label="conflict"))
        holder.commit()
    t.join(10)
    assert result == [409]
    with Session(db) as s:
        assert s.get_one(Answer, answer_id).approved_at is None


def test_not_applicable_clears_what_the_engine_stored(db: Engine, ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    answer_id = _answer_id(client, run)
    client.post(f"/api/answers/{answer_id}/approve")
    client.post(f"/api/answers/{answer_id}/not-applicable", json={"reason": "We take no card data."})
    with Session(db) as s:
        a = s.get_one(Answer, answer_id)
        assert (a.citations, a.dropped, a.conflict, a.scope_note, a.statement_id) == (
            [],
            [],
            None,
            None,
            None,
        )
        assert (a.stances, a.chunk_ids, a.retrieval_dropped, a.approved_at, a.value) == (
            [],
            [],
            [],
            None,
            None,
        )
        reason = s.query(AuditEvent).filter_by(action="answer.not_applicable").one().detail["reason"]
    assert reason == "We take no card data."
    d = client.get(f"/api/answers/{answer_id}").json()
    assert d["citations"] == [] and d["sources"] == 0 and d["conflict"] is None


def test_a_conflict_cannot_be_approved(db: Engine, ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    with Session(db) as s:
        s.execute(Answer.__table__.update().values(label="conflict", citations=[f.CITATION]))
        s.commit()
    r = client.post(f"/api/answers/{_answer_id(client, run)}/approve")
    assert r.status_code == 409 and "conflict" in r.json()["detail"]


def test_an_unknown_answer_cannot_be_approved(db: Engine, ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    with Session(db) as s:
        s.execute(Answer.__table__.update().values(label="unknown", citations=[]))
        s.commit()
    r = client.post(f"/api/answers/{_answer_id(client, run)}/approve")
    assert r.status_code == 409 and r.json()["detail"] == "Answer the question for this item first."


def test_another_workspaces_ids_are_a_404(db: Engine, ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    run = _run_to_end(client, qid)
    answer_id = _answer_id(client, run)
    other, _ = visitor(db)
    for method, path, body in [
        ("GET", f"/api/runs/{run['id']}", None),
        ("GET", f"/api/runs/{run['id']}/answers", None),
        ("POST", f"/api/runs/{run['id']}/step", None),
        ("POST", f"/api/runs/{run['id']}/approve-verified", None),
        ("POST", f"/api/questionnaires/{qid}/runs", None),
        ("GET", f"/api/answers/{answer_id}", None),
        ("PATCH", f"/api/answers/{answer_id}", {"text": "x"}),
        ("POST", f"/api/answers/{answer_id}/approve", None),
        ("POST", f"/api/answers/{answer_id}/not-applicable", {"reason": "x"}),
    ]:
        r = other.request(method, path, json=body)
        assert (r.status_code, r.json()) == (404, {"detail": "Not found."}), path


def test_step_calls_are_limited_per_network(ready, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setitem(ip_limits.LIMITS, "llm", (0, ip_limits.LIMITS["llm"][1]))
    client, qid = ready
    run = client.post(f"/api/questionnaires/{qid}/runs").json()
    r = client.post(f"/api/runs/{run['id']}/step")
    assert r.status_code == 429 and "retry-after" in r.headers
    assert client.get(f"/api/runs/{run['id']}").json()["done"] == 0


def test_without_a_model_key_a_step_is_a_503(ready) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    app.dependency_overrides[get_llm] = lambda: None
    run = client.post(f"/api/questionnaires/{qid}/runs").json()
    assert client.post(f"/api/runs/{run['id']}/step").status_code == 503


def test_a_questionnaire_without_items_cannot_run(db: Engine) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        q = f.questionnaire(s, s.get_one(Workspace, ws_id))
        s.commit()
        qid = q.id
    assert client.post(f"/api/questionnaires/{qid}/runs").status_code == 422


def test_the_audit_log_lists_this_workspaces_events_only(ready, db: Engine) -> None:  # type: ignore[no-untyped-def]
    client, qid = ready
    _run_to_end(client, qid)
    with Session(db) as s:
        other = f.workspace(s)
        s.add(AuditEvent(workspace_id=other.id, actor="visitor", action="document.upload"))
        s.commit()
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert actions == ["run.done", "run.create"]


@pytest.mark.parametrize("reason", get_args(DropReason))
def test_every_drop_reason_has_a_sentence_and_a_schema_value(reason: str) -> None:
    # final review I2: a stored "statement" drop (6B) must not KeyError (a 500) in the evidence drawer
    assert set(WHY) == set(get_args(DropReason))
    out = DroppedOut(reason=reason, document_id=uuid.uuid4(), filename="a.md", line=1, sentence=WHY[reason])
    assert out.reason == reason

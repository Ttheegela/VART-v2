import io
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.api import documents as api
from app.db.models import AuditEvent, Document, Run, SuggestedFill, Workspace
from app.main import app
from app.services import ip_limits
from datakit.schemas import Facts, load_yaml
from tests import factories as f
from tests.apiclient import visitor

MD = b"# Access policy\n\nScope: internal systems\n\nAccess is reviewed quarterly.\n"


def _upload(client, name: str = "access-policy.md", data: bytes = MD):  # type: ignore[no-untyped-def]
    return client.post("/api/documents", files={"file": (name, io.BytesIO(data), "application/octet-stream")})


def test_an_upload_is_parsed_classified_and_listed(db: Engine) -> None:
    client, _ = visitor(db)
    r = _upload(client)
    assert r.status_code == 201
    body = r.json()
    assert (body["filename"], body["source"], body["kind"], body["line_count"]) == (
        "access-policy.md",
        "upload",
        "policy",
        3,
    )
    assert [d["id"] for d in client.get("/api/documents").json()] == [body["id"]]


def test_a_refused_file_is_a_422_with_a_sentence_and_nothing_is_stored(db: Engine) -> None:
    client, _ = visitor(db)
    r = _upload(client, "evil.xlsx", b"PK\x03\x04not a zip")
    assert r.status_code == 422 and r.json()["detail"].endswith(".")
    assert client.get("/api/documents").json() == []


def test_the_size_limit_is_checked_on_the_bytes(db: Engine) -> None:
    client, _ = visitor(db)
    r = _upload(client, "big.md", b"x" * (4 * 1024 * 1024 + 1))
    assert r.status_code == 422 and r.json()["detail"] == "Files must be 4 MB or smaller."


def test_uploads_are_limited_per_network(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "upload", (1, ip_limits.LIMITS["upload"][1]))
    client, _ = visitor(db)
    assert _upload(client).status_code == 201
    r = _upload(client, "second.md")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_an_upload_into_a_deleted_workspace_is_a_404(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    # Carry-over: the workspace vanishes between the cookie check and the insert (reset in another tab).
    client, _ = visitor(db)
    real = api.ingest_document

    def reset_first(session, *a, **kw):  # type: ignore[no-untyped-def]
        with db.begin() as conn:
            conn.execute(text("delete from workspaces"))
        return real(session, *a, **kw)

    monkeypatch.setattr(api, "ingest_document", reset_first)
    r = _upload(client)
    assert r.status_code == 404 and "reload the page" in r.json()["detail"]


def test_a_cross_site_write_is_refused(db: Engine) -> None:
    client, _ = visitor(db)
    r = client.post(
        "/api/documents",
        files={"file": ("a.md", io.BytesIO(MD), "text/plain")},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403
    assert client.get("/api/documents").json() == []


def test_the_sample_pack_loads_once_in_fact_sheet_order(db: Engine) -> None:
    facts = load_yaml(api.SAMPLE_DIR.parent / "facts.yaml", Facts)
    assert list(api.SAMPLE_ORDER) == [d.filename for d in facts.documents]
    client, _ = visitor(db)
    first = client.post("/api/documents/sample")
    assert first.status_code == 201 and len(first.json()) == 23
    assert [d["filename"] for d in first.json()] == list(api.SAMPLE_ORDER)
    again = client.post("/api/documents/sample")
    assert [d["id"] for d in again.json()] == [d["id"] for d in first.json()]


def test_two_tabs_loading_the_sample_at_once_store_it_once(db: Engine) -> None:
    # Pre-flight P19: the workspace row is locked and the name re-checked.
    client, ws_id = visitor(db)
    other = TestClient(app, cookies=client.cookies)
    results: list[int] = []
    gate = threading.Barrier(2)

    def load(c: TestClient) -> None:
        gate.wait()
        results.append(c.post("/api/documents/sample").status_code)

    threads = [threading.Thread(target=load, args=(c,)) for c in (client, other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [201, 201]
    with Session(db) as s:
        n = s.scalar(select(func.count()).select_from(Document).where(Document.workspace_id == ws_id))
        names = s.scalars(select(Document.filename).where(Document.workspace_id == ws_id)).all()
    assert n == 23 and len(set(names)) == 23


def test_a_metadata_override_is_stored_as_the_users(db: Engine) -> None:
    client, _ = visitor(db)
    doc = _upload(client).json()
    r = client.patch(f"/api/documents/{doc['id']}", json={"status": "draft", "evidence_allowed": False})
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["evidence_allowed"], body["metadata_source"], body["redecided"]) == (
        "draft",
        False,
        "user",
        0,
    )


@pytest.mark.parametrize("field", ["kind", "status", "evidence_allowed"])
def test_a_patch_may_not_null_a_required_field(db: Engine, field: str) -> None:
    client, _ = visitor(db)
    doc = _upload(client).json()
    assert client.patch(f"/api/documents/{doc['id']}", json={field: None}).status_code == 422


def test_a_patch_may_clear_the_scope_and_date(db: Engine) -> None:
    client, _ = visitor(db)
    doc = _upload(client).json()
    r = client.patch(f"/api/documents/{doc['id']}", json={"scope": None, "effective_date": None})
    assert r.status_code == 200 and (r.json()["scope"], r.json()["effective_date"]) == (None, None)


def test_an_empty_patch_changes_nothing(db: Engine) -> None:
    client, ws_id = visitor(db)
    doc = _upload(client).json()
    r = client.patch(f"/api/documents/{doc['id']}", json={})
    assert r.status_code == 200 and r.json()["metadata_source"] == doc["metadata_source"]
    with Session(db) as s:
        actions = s.scalars(select(AuditEvent.action).where(AuditEvent.workspace_id == ws_id)).all()
    assert actions == ["document.upload"]


@pytest.mark.parametrize(
    "patch", [{"kind": "policy"}, {"status": "draft"}, {"evidence_allowed": False}, {"scope": "production"}]
)
def test_a_statement_is_the_visitors_answer_and_its_metadata_cannot_change(
    db: Engine, patch: dict[str, object]
) -> None:
    """adversary-2 I1 and M7: a kind patch would pass the visitor's own answer off as document evidence, and
    the engine keeps a statement's other details (nothing re-decides on them)."""
    client, ws_id = visitor(db)
    with Session(db) as s:
        stmt = f.document(
            s, s.get_one(Workspace, ws_id), source="statement", filename="answer-001.txt", kind="statement"
        )
        s.commit()
        stmt_id = stmt.id
    r = client.patch(f"/api/documents/{stmt_id}", json=patch)
    assert r.status_code == 409 and r.json()["detail"] == api.STATEMENT_FIXED
    with Session(db) as s:
        d = s.get_one(Document, stmt_id)
        assert (d.kind, d.status, d.evidence_allowed, d.scope) == ("statement", "final", True, None)


def test_another_workspaces_document_is_a_404(db: Engine) -> None:
    client, _ = visitor(db)
    with Session(db) as s:
        other = f.document(s, f.workspace(s))
        s.commit()
        other_id = other.id
    assert client.patch(f"/api/documents/{other_id}", json={"status": "draft"}).status_code == 404
    assert client.get(f"/api/documents/{other_id}/lines").status_code == 404
    assert client.delete(f"/api/documents/{other_id}").status_code == 404


def test_lines_are_read_in_a_bounded_window(db: Engine) -> None:
    client, _ = visitor(db)
    doc = _upload(client).json()
    r = client.get(f"/api/documents/{doc['id']}/lines", params={"from": 2, "to": 3})
    assert [x["n"] for x in r.json()["lines"]] == [2, 3]
    assert client.get(f"/api/documents/{doc['id']}/lines", params={"from": 1, "to": 5000}).status_code == 422


def test_an_unused_document_is_deleted(db: Engine) -> None:
    client, _ = visitor(db)
    doc = _upload(client).json()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json() == []


def test_a_document_a_run_used_cannot_be_deleted(db: Engine) -> None:
    client, ws_id = visitor(db)
    doc = _upload(client).json()
    with Session(db) as s:
        chunk_id = s.execute(text("select id from chunks where document_id = :d"), {"d": doc["id"]}).scalar()
        ws = s.get_one(Workspace, ws_id)
        q = f.questionnaire(s, ws)
        f.answer(s, f.run(s, q), f.item(s, q), chunk_ids=[str(chunk_id)])
        s.commit()
    r = client.delete(f"/api/documents/{doc['id']}")
    assert r.status_code == 409


def test_a_statement_a_suggestion_cites_cannot_be_deleted(db: Engine) -> None:
    # Pre-flight P20: a NO ACTION foreign key must read as 409, not as "workspace gone".
    client, ws_id = visitor(db)
    with Session(db) as s:
        ws = s.get_one(Workspace, ws_id)
        stmt = f.document(s, ws, source="statement", filename="answer-1.txt", kind="statement")
        q = f.questionnaire(s, ws)
        s.add(
            SuggestedFill(
                workspace_id=ws.id,
                run_id=f.run(s, q).id,
                item_id=f.item(s, q).id,
                statement_id=stmt.id,
                label="partial",
                citations=[f.CITATION],
            )
        )
        s.commit()
        stmt_id = stmt.id
    assert client.delete(f"/api/documents/{stmt_id}").status_code == 409


def test_every_action_is_audited_without_document_text(db: Engine) -> None:
    client, ws_id = visitor(db)
    _upload(client)
    with Session(db) as s:
        events = s.query(AuditEvent).filter_by(workspace_id=ws_id).all()
    assert [e.action for e in events] == ["document.upload"]
    assert "quarterly" not in str(events[0].detail)


def test_a_delete_waits_for_a_run_being_created_and_then_refuses(db: Engine) -> None:
    # Final review M8: the run check is not a stale read; the workspace row lock waits out the run's insert.
    client, ws_id = visitor(db)
    doc_id = _upload(client).json()["id"]
    result: list[int] = []
    with Session(db) as creator:
        ws = creator.get_one(Workspace, ws_id)
        creator.add(Run(workspace_id=ws_id, questionnaire_id=f.questionnaire(creator, ws).id, models={}))
        creator.flush()  # the run exists but is not committed: it holds a key-share lock on the workspace row

        def delete() -> None:
            result.append(client.delete(f"/api/documents/{doc_id}").status_code)

        th = threading.Thread(target=delete)
        th.start()
        time.sleep(0.5)
        assert th.is_alive()
        creator.commit()
    th.join(10)
    assert result == [409]

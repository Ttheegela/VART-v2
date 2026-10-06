import io
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.api import documents
from app.db.models import Item, Questionnaire
from app.main import app
from app.services import capacity, ip_limits
from tests import factories as f
from tests.apiclient import visitor

MAPPER = Path(__file__).resolve().parent.parent / "data" / "mapper"


def _post(client, name: str):  # type: ignore[no-untyped-def]
    data = (MAPPER / name).read_bytes()
    return client.post(
        "/api/questionnaires", files={"file": (name, io.BytesIO(data), "application/octet-stream")}
    )


def test_an_upload_answers_the_detected_mapping_and_a_preview_without_items(db: Engine) -> None:
    client, _ = visitor(db)
    r = _post(client, "v04.xlsx")
    assert r.status_code == 201
    body = r.json()
    assert body["detected"]["header_row"] == 3 and body["mapping"] is None and body["item_count"] == 0
    assert len(body["preview"]) == 8 and body["preview"][0]["question"].endswith("?")


def test_confirming_the_mapping_creates_the_items(db: Engine) -> None:
    client, _ = visitor(db)
    q = _post(client, "v05.xlsx").json()
    r = client.put(f"/api/questionnaires/{q['id']}/mapping", json=q["detected"])
    assert r.status_code == 200
    body = r.json()
    assert body["item_count"] == 20 and body["items"][0]["topic"] == "GOVERNANCE"
    assert [i["position"] for i in body["items"]] == list(range(1, 21))


def test_a_mapping_that_reads_no_items_is_a_422(db: Engine) -> None:
    client, _ = visitor(db)
    q = _post(client, "v01.xlsx").json()
    wrong = q["detected"] | {"question_col": "C"}  # the empty comments column
    assert client.put(f"/api/questionnaires/{q['id']}/mapping", json=wrong).status_code == 422


def test_the_samples_load_mapped(db: Engine) -> None:
    client, _ = visitor(db)
    r = client.post("/api/questionnaires/sample/vsq-a")
    assert r.status_code == 201 and r.json()["item_count"] == 64 and r.json()["source"] == "sample"
    assert client.post("/api/questionnaires/sample/nope").status_code == 404
    assert len(client.get("/api/questionnaires").json()) == 1


# ------------------------------------------------------------------ Task 5 lane additions
def _csv(client, rows: str, name: str = "q.csv"):  # type: ignore[no-untyped-def]
    return client.post("/api/questionnaires", files={"file": (name, io.BytesIO(rows.encode()), "text/csv")})


def _count(db: Engine, ws_id: uuid.UUID, model: type) -> int:
    with Session(db) as s:
        return s.scalar(select(func.count()).select_from(model).where(model.workspace_id == ws_id)) or 0  # type: ignore[attr-defined]


def test_the_sample_is_idempotent_and_counted_once(db: Engine) -> None:
    client, ws_id = visitor(db)
    first = client.post("/api/questionnaires/sample/mvsp-b")
    again = client.post("/api/questionnaires/sample/mvsp-b")
    assert (first.status_code, again.status_code) == (201, 201) and first.json()["id"] == again.json()["id"]
    assert _count(db, ws_id, Questionnaire) == 1
    assert first.json()["mapping"] is not None and first.json()["format"] == "csv"


def test_two_tabs_loading_a_sample_at_once_store_it_once(db: Engine) -> None:
    client, ws_id = visitor(db)
    other = TestClient(app, cookies=client.cookies)
    results: list[int] = []
    gate = threading.Barrier(2)

    def load(c: TestClient) -> None:
        gate.wait()
        results.append(c.post("/api/questionnaires/sample/vsq-a").status_code)

    threads = [threading.Thread(target=load, args=(c,)) for c in (client, other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [201, 201]
    assert _count(db, ws_id, Questionnaire) == 1 and _count(db, ws_id, Item) == 64


def test_a_new_sample_counts_under_the_upload_limit_but_a_repeat_does_not(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "upload", (1, ip_limits.LIMITS["upload"][1]))
    client, _ = visitor(db)
    assert client.post("/api/questionnaires/sample/vsq-a").status_code == 201
    assert client.post("/api/questionnaires/sample/vsq-a").status_code == 201  # already stored: not counted
    r = client.post("/api/questionnaires/sample/mvsp-b")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_a_sample_is_refused_when_the_demo_is_full(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = visitor(db)
    monkeypatch.setattr(capacity, "demo_is_full", lambda session: True)
    assert client.post("/api/questionnaires/sample/vsq-a").status_code == 503


def test_a_file_over_1_mb_and_a_long_sheet_name_are_422(db: Engine) -> None:
    client, _ = visitor(db)
    r = _csv(client, "Question\n" + "x" * (1024 * 1024))
    assert r.status_code == 422 and "1 MB" in r.json()["detail"]
    wb = openpyxl.Workbook()
    wb.active.title = "S" * 31
    buf = io.BytesIO()
    wb.save(buf)
    ok = client.post(
        "/api/questionnaires", files={"file": ("a.xlsx", buf.getvalue(), "application/octet-stream")}
    )
    assert ok.status_code == 201 and ok.json()["sheets"] == ["S" * 31]


@pytest.fixture
def csf_allowed(db: Engine) -> Iterator[None]:
    """Plan 6B adds `csf` to ck_questionnaires_source; until then the test lifts the check."""
    with db.begin() as c:
        c.execute(text("alter table questionnaires drop constraint ck_questionnaires_source"))
    try:
        yield
    finally:
        with db.begin() as c:
            c.execute(text("delete from questionnaires where source = 'csf'"))
            c.execute(
                text(
                    "alter table questionnaires add constraint ck_questionnaires_source "
                    "check (source in ('sample', 'upload', 'drive'))"
                )
            )


def test_a_sixth_questionnaire_is_a_422_and_a_csf_one_does_not_count(db: Engine, csf_allowed: None) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        s.add(Questionnaire(workspace_id=ws_id, filename="csf", source="csf"))
        s.commit()
    for n in range(5):
        assert _csv(client, "Question\nIs it in place?\n", f"q{n}.csv").status_code == 201
    r = _csv(client, "Question\nIs it in place?\n", "q6.csv")
    assert r.status_code == 422 and "5" in r.json()["detail"]
    assert len(client.get("/api/questionnaires").json()) == 5  # the csf one is left out


def test_a_mapping_is_cached_so_a_get_does_not_read_the_file(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = visitor(db)
    q = _post(client, "v05.xlsx").json()

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("the file was parsed again")

    monkeypatch.setattr("app.api.questionnaires.read_sheets", boom)
    assert client.get("/api/questionnaires").json()[0]["sheets"] == q["sheets"]
    assert client.get(f"/api/questionnaires/{q['id']}").json()["preview"] == q["preview"]


def test_remapping_replaces_the_items_and_a_run_freezes_it(db: Engine) -> None:
    client, ws_id = visitor(db)
    q = _post(client, "v05.xlsx").json()
    assert client.put(f"/api/questionnaires/{q['id']}/mapping", json=q["detected"]).status_code == 200
    assert client.put(f"/api/questionnaires/{q['id']}/mapping", json=q["detected"]).json()["item_count"] == 20
    with Session(db) as s:
        f.run(s, s.get(Questionnaire, uuid.UUID(q["id"])))  # type: ignore[arg-type]
        s.commit()
    r = client.put(f"/api/questionnaires/{q['id']}/mapping", json=q["detected"])
    assert r.status_code == 409
    assert client.get(f"/api/questionnaires/{q['id']}").json()["latest_run_id"] is not None


def test_a_mapping_for_a_sheet_that_is_not_there_is_a_422(db: Engine) -> None:
    client, _ = visitor(db)
    q = _post(client, "v05.xlsx").json()
    r = client.put(f"/api/questionnaires/{q['id']}/mapping", json=q["detected"] | {"sheet": "Nope"})
    assert r.status_code == 422


def test_delete_removes_items_and_is_refused_after_a_run(db: Engine) -> None:
    client, ws_id = visitor(db)
    a = client.post("/api/questionnaires/sample/vsq-a").json()
    b = client.post("/api/questionnaires/sample/mvsp-b").json()
    assert client.delete(f"/api/questionnaires/{a['id']}").status_code == 204
    assert client.get(f"/api/questionnaires/{a['id']}").status_code == 404
    assert client.delete(f"/api/questionnaires/{a['id']}").status_code == 404
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(Item).where(Item.workspace_id == ws_id)) == len(
            client.get(f"/api/questionnaires/{b['id']}").json()["items"]
        )
        f.run(s, s.get(Questionnaire, uuid.UUID(b["id"])))  # type: ignore[arg-type]
        s.commit()
    assert client.delete(f"/api/questionnaires/{b['id']}").status_code == 409
    assert len(client.get("/api/questionnaires").json()) == 1


def test_a_csf_questionnaire_is_not_deletable_or_mappable(db: Engine, csf_allowed: None) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        q = Questionnaire(workspace_id=ws_id, filename="csf", source="csf")
        s.add(q)
        s.commit()
        qid = q.id
    assert client.delete(f"/api/questionnaires/{qid}").status_code == 404
    mapping = {
        "sheet": None,
        "header_row": 1,
        "id_col": None,
        "question_col": "A",
        "answer_col": "B",
        "comments_col": None,
    }
    assert client.put(f"/api/questionnaires/{qid}/mapping", json=mapping).status_code == 409
    body = client.get(f"/api/questionnaires/{qid}").json()
    assert body["format"] == "builtin" and body["sheets"] == []


def test_another_workspaces_questionnaire_is_a_404(db: Engine) -> None:
    mine, _ = visitor(db)
    theirs, _ = visitor(db)
    q = _post(theirs, "v05.xlsx").json()
    assert mine.get(f"/api/questionnaires/{q['id']}").status_code == 404
    assert mine.delete(f"/api/questionnaires/{q['id']}").status_code == 404


def test_a_cross_site_upload_is_a_403(db: Engine) -> None:
    client, _ = visitor(db)
    r = client.post("/api/questionnaires/sample/vsq-a", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_the_documents_sample_load_makes_no_model_call(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    # Task 4 guard: the sample documents are classified by rules alone (llm None, no budget spent).
    real = documents.classify
    seen: list[object] = []

    def spy(name, parsed, llm, model, spend):  # type: ignore[no-untyped-def]
        seen.append(llm)
        return real(name, parsed, llm, model, spend)

    monkeypatch.setattr(documents, "classify", spy)
    client, _ = visitor(db)
    assert client.post("/api/documents/sample").status_code == 201
    assert seen and all(llm is None for llm in seen)

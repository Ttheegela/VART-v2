import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import sample_run
from app.api.deps import get_llm
from app.db.models import LlmUsage, Run
from app.main import app
from app.settings import get_settings
from scripts.sample_snapshot import build
from tests.apiclient import visitor
from tests.fakes import ByStepLLM

ROOT = Path(__file__).resolve().parent.parent
REGENERATE = "stale sample snapshot: run `python scripts/sample_snapshot.py` (no key needed) and commit it"


def _sample(client: TestClient, name: str = "vsq-a") -> dict[str, Any]:
    assert client.post("/api/documents/sample").status_code == 201
    q = client.post(f"/api/questionnaires/sample/{name}").json()
    res = client.post(f"/api/questionnaires/{q['id']}/runs")
    assert res.status_code == 201, res.text
    return {"q": q, "run": res.json()}


def test_the_snapshot_is_what_the_recordings_give(db: Engine) -> None:
    client, _ = visitor(db)
    committed = json.loads(sample_run.SNAPSHOT.read_text(encoding="utf-8"))
    assert build(client, db) == committed, REGENERATE


def test_the_snapshot_covers_both_samples_and_the_core_gap_check() -> None:
    snap = sample_run.snapshot()
    assert snap is not None, REGENERATE
    assert snap["digest"] == sample_run.digest(get_settings().models()), REGENERATE
    sizes = {name: len(q["items"]) for name, q in snap["questionnaires"].items()}
    assert sizes == {"vsq-a.xlsx": 64, "mvsp-b.csv": 25} and len(snap["gap"]["items"]) == 36


def test_the_digest_moves_with_the_models_and_the_documents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    models = dict(get_settings().models())
    base = sample_run.digest(models)
    assert sample_run.digest({**models, "stance": "other/model"}) != base
    assert sample_run.digest({**models, "classify": "other/model"}) == base  # the sample load uses no model
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in sample_run.SAMPLE_ORDER:
        (docs / name).write_bytes((sample_run.DOCS / name).read_bytes())
    (docs / sample_run.SAMPLE_ORDER[0]).write_bytes(b"changed")
    monkeypatch.setattr(sample_run, "DOCS", docs)
    sample_run._digest.cache_clear()
    try:
        assert sample_run.digest(models) != base
    finally:
        monkeypatch.undo()
        sample_run._digest.cache_clear()


@pytest.mark.parametrize(("name", "items"), [("vsq-a", 64), ("mvsp-b", 25)])
def test_try_with_a_sample_company_copies_the_snapshot_with_no_model_call(
    db: Engine, name: str, items: int
) -> None:
    client, ws_id = visitor(db)
    run = _sample(client, name)["run"]
    assert (run["status"], run["total"], run["done"], run["cost_usd"], run["precomputed"]) == (
        "done",
        items,
        items,
        0.0,
        True,
    )
    rows = client.get(f"/api/runs/{run['id']}/answers").json()["rows"]
    own = {d["id"] for d in client.get("/api/documents").json()}
    cited = [r["answer"] for r in rows if r["answer"]["label"] in ("verified", "partial")]
    assert cited
    for a in cited:
        detail = client.get(f"/api/answers/{a['id']}").json()
        assert detail["citations"]
        for c in detail["citations"]:
            assert c["document_id"] in own and c["found_in_source"], c  # the visitor's own copies
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(LlmUsage).where(LlmUsage.workspace_id == ws_id)) == 0


def test_re_run_live_runs_the_engine(db: Engine) -> None:
    client, _ = visitor(db)
    q = _sample(client)["q"]
    live = client.post(f"/api/questionnaires/{q['id']}/runs", params={"live": "true"}).json()
    assert (live["status"], live["precomputed"], live["done"]) == ("running", False, 0)


def test_an_override_or_an_upload_falls_back_to_a_live_run(db: Engine) -> None:
    client, _ = visitor(db)
    q = _sample(client)["q"]
    doc = client.get("/api/documents").json()[0]
    assert client.patch(f"/api/documents/{doc['id']}", json={"status": "draft"}).status_code == 200
    after = client.post(f"/api/questionnaires/{q['id']}/runs").json()
    assert (after["status"], after["precomputed"]) == ("running", False)
    other, _ = visitor(db)
    q2 = _sample(other)["q"]
    files = {"file": ("notes.md", b"# Notes\n\nBackups are tested every quarter.\n", "text/markdown")}
    assert other.post("/api/documents", files=files).status_code == 201
    assert other.post(f"/api/questionnaires/{q2['id']}/runs").json()["precomputed"] is False


def test_a_stale_snapshot_is_never_copied(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    real = sample_run.snapshot()
    assert real is not None
    monkeypatch.setattr(sample_run, "snapshot", lambda: {**real, "digest": "0" * 16})
    client, _ = visitor(db)
    assert _sample(client)["run"]["status"] == "running"


def test_version_says_whether_the_sample_is_precomputed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    assert client.get("/api/version").json()["sample_precomputed"] is True
    monkeypatch.setenv("STANCE_MODEL", "other/model")
    assert client.get("/api/version").json()["sample_precomputed"] is False


def test_questions_rechecks_and_redecide_work_on_a_copied_run(db: Engine) -> None:
    client, _ = visitor(db)
    run = _sample(client)["run"]
    questions = client.get(f"/api/runs/{run['id']}/questions").json()
    assert questions  # the copied run has open items, planned as for any done run
    reply = json.dumps({"passages": [{"passage": 1, "stance": "irrelevant", "quote": "", "note": "x"}]})
    app.dependency_overrides[get_llm] = lambda: ByStepLLM({"recheck": reply})
    try:
        res = client.post(
            f"/api/questions/{questions[0]['id']}/answer",
            json={"text": "Yes. The security team reviews this every quarter and keeps a record."},
        )
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert res.status_code == 200 and res.json()["question"]["status"] in ("answered", "follow_up")
    doc = client.get("/api/documents").json()[0]
    assert client.patch(f"/api/documents/{doc['id']}", json={"evidence_allowed": False}).status_code == 200


def test_the_core_gap_check_is_copied_too(db: Engine) -> None:
    client, _ = visitor(db)
    assert client.post("/api/documents/sample").status_code == 201
    run = client.post("/api/gap/core/run").json()
    assert (run["status"], run["done"], run["cost_usd"], run["precomputed"]) == ("done", 36, 0.0, True)
    rows = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    assert all(r["label"] for r in rows.values() if r["tier"] == "checked")
    detail = client.get(f"/api/answers/{rows['PR.DS-11']['answer_id']}").json()
    assert len(detail["parts"]) == 4
    assert all(c["found_in_source"] for p in detail["parts"] for c in p["citations"])
    again = client.post("/api/gap/core/run").json()  # Check again: only the sample pack, nothing changed
    assert (again["id"], again["status"]) == (run["id"], "done")
    assert client.post("/api/gap/protect/run").json()["status"] == "running"  # a function scope runs live


def test_the_snapshot_ships_with_the_function() -> None:
    lines = (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
    assert "!/data/dev/sample-run.json" in lines


def test_a_double_press_makes_one_copied_run(db: Engine) -> None:
    # adversary-1 M6: the copy path skips create_run's lock, so it reuses the current copy itself
    client, ws_id = visitor(db)
    first = _sample(client)
    again = client.post(f"/api/questionnaires/{first['q']['id']}/runs").json()
    assert (again["id"], again["precomputed"]) == (first["run"]["id"], True)
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(Run).where(Run.workspace_id == ws_id)) == 1


def test_a_workspace_chunked_differently_is_never_copied(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    # adversary-1 M7: a workspace chunked by an older deploy keeps its chunk names but not their boundaries
    real = sample_run.snapshot()
    assert real is not None
    name = sample_run.SAMPLE_ORDER[0]
    chunks = {**real["chunks"], name: real["chunks"][name] + 1}
    monkeypatch.setattr(sample_run, "snapshot", lambda: {**real, "chunks": chunks})
    client, _ = visitor(db)
    assert _sample(client)["run"]["precomputed"] is False
    assert client.post("/api/gap/core/run").json()["precomputed"] is False


def test_the_snapshot_holds_only_public_fields() -> None:
    # adversary-1 Q8: sample-pack answers, model names, prompt versions and chunk counts; no id, no workspace
    # data
    snap = sample_run.snapshot()
    assert snap is not None, REGENERATE
    assert set(snap) == {"digest", "models", "prompt_versions", "chunks", "questionnaires", "gap"}
    assert sorted(snap["chunks"]) == sorted(sample_run.SAMPLE_ORDER)
    entries = [e for q in snap["questionnaires"].values() for e in q["items"]] + snap["gap"]["items"]
    for e in entries:
        assert set(e) <= {"position", "question", "topic", "csf_id", "values", "parts"}
        assert set(e["values"]) == set(sample_run.ANSWER_FIELDS)

"""Write data/dev/sample-run.json (Plan 4 Task 3): the bundled sample questionnaires (vsq-a, mvsp-b) and the
core gap check, run by the real endpoints over the sample pack with every model reply replayed
from the committed eval recordings, so no key is used and nothing is spent. Nobody edits the file by hand.

    SESSION_SECRET=snapshot-only DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test \\
        python scripts/sample_snapshot.py

tests/test_sample_run.py::test_the_snapshot_is_what_the_recordings_give runs build() in CI and fails on any
difference: after a re-recording or a prompt, model, engine or sample-data change, run this and commit the
file."""

import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import sample_run  # noqa: E402
from app.api.deps import get_llm  # noqa: E402
from app.db.models import Answer, Chunk, Document, Item, Run, RunItem  # noqa: E402
from app.db.session import database_url, get_engine  # noqa: E402
from app.llm.recorder import ReplayClient  # noqa: E402
from app.main import app  # noqa: E402
from app.runs import FAILED_TEXT  # noqa: E402
from app.settings import get_settings  # noqa: E402

RECORDED = ROOT / "evals" / "recorded"
SAMPLES = {"vsq-a": "vsq-a.xlsx", "mvsp-b": "mvsp-b.csv"}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _finish(client: TestClient, run_id: str) -> None:
    while client.get(f"/api/runs/{run_id}").json()["status"] == "running":
        res = client.post(f"/api/runs/{run_id}/step")
        if res.status_code != 200:
            raise SystemExit(f"step failed: {res.status_code} {res.text[:300]}")


def _names(s: Session, workspace_id: uuid.UUID) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
    rows = s.execute(
        select(Chunk.id, Chunk.line_start, Document.id, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.workspace_id == workspace_id)
    ).all()
    chunks = {str(cid): f"{name}#{line}" for cid, line, _, name in rows}
    if len(set(chunks.values())) != len(chunks):
        raise SystemExit("two chunks of one document start on the same line: the snapshot cannot name them")
    counts = dict(Counter(name for _, _, _, name in rows))
    return chunks, {str(did): name for _, _, did, name in rows}, counts


def _entries(
    s: Session, run_id: uuid.UUID, chunks: dict[str, str], docs: dict[str, str]
) -> list[dict[str, Any]]:
    rows = s.execute(
        select(Item, Answer, RunItem.parts)
        .join(Answer, (Answer.item_id == Item.id) & (Answer.run_id == run_id))
        .join(RunItem, (RunItem.item_id == Item.id) & (RunItem.run_id == run_id))
        .order_by(Item.position)
    ).tuples()
    out: list[dict[str, Any]] = []
    for item, a, parts in rows:
        if a.text == FAILED_TEXT or a.statement_id is not None:
            raise SystemExit(f"{item.code}: not a clean engine answer; check the recordings")
        values = {k: getattr(a, k) for k in sample_run.ANSWER_FIELDS}
        entry: dict[str, Any] = {
            "position": item.position,
            "question": item.question,
            "topic": item.topic,
            "csf_id": item.csf_id,
            "values": sample_run.swap(values, chunks.__getitem__, docs.__getitem__),
        }
        if parts:
            entry["parts"] = sample_run.swap(parts, chunks.__getitem__, docs.__getitem__)
        out.append(entry)
    return out


def _workspace_id(s: Session, run_id: str) -> uuid.UUID:
    return s.get_one(Run, uuid.UUID(run_id)).workspace_id


def build(client: TestClient, engine: Engine) -> dict[str, Any]:
    """The snapshot, from fresh workspaces on `client`'s cookie. Resets the workspace when done. The two
    questionnaires run in one workspace and the core gap check in a second, fresh one (preflight B1): 64 + 25
    + 73 stance calls in one workspace would pass the per-workspace stance cap (150 an hour), and the caps
    stay as they are. Chunk names are "<file>#<line>", the same in both workspaces; each run is named by its
    own workspace."""
    models = get_settings().models()
    sample_run.ENABLED = False  # never copy the old snapshot while making the new one
    try:
        assert client.get("/api/workspace").status_code == 200
        assert client.post("/api/documents/sample").status_code == 201
        app.dependency_overrides[get_llm] = lambda: ReplayClient(RECORDED / "dev.jsonl")
        runs: dict[str, str] = {}
        for name, filename in SAMPLES.items():
            q = client.post(f"/api/questionnaires/sample/{name}").json()
            run = client.post(f"/api/questionnaires/{q['id']}/runs", params={"live": "true"}).json()
            _finish(client, run["id"])
            runs[filename] = run["id"]
        with Session(engine) as s:
            first = _workspace_id(s, runs[SAMPLES["vsq-a"]])
            named = _names(s, first)
            questionnaires = {f: {"items": _entries(s, uuid.UUID(r), *named[:2])} for f, r in runs.items()}
        assert client.post("/api/workspace/reset").status_code == 204
        assert client.get("/api/workspace").status_code == 200
        assert client.post("/api/documents/sample").status_code == 201
        app.dependency_overrides[get_llm] = lambda: ReplayClient(RECORDED / "gap-dev.jsonl")
        gap = client.post("/api/gap/core/run").json()
        _finish(client, gap["id"])
    finally:
        app.dependency_overrides.pop(get_llm, None)
        sample_run.ENABLED = True
    with Session(engine) as s:
        g = s.get_one(Run, uuid.UUID(gap["id"]))
        gap_named = _names(s, g.workspace_id)
        if gap_named[2] != named[2]:
            raise SystemExit("the two workspaces chunked the sample pack differently")
        snap = {
            "digest": sample_run.digest(models),
            "models": {step: models[step] for step in sample_run.STEPS},
            "prompt_versions": g.prompt_versions,
            "chunks": named[2],
            "questionnaires": questionnaires,
            "gap": {"scope": "core", "items": _entries(s, g.id, *gap_named[:2])},
        }
    text = json.dumps(snap, sort_keys=True, ensure_ascii=False)
    if found := _UUID.search(text):
        raise SystemExit(f"an id the snapshot does not map: {found.group()}")
    client.post("/api/workspace/reset")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def main() -> int:
    if "test" not in (make_url(database_url()).database or ""):
        print("refusing to run: DATABASE_URL must point at a test database", file=sys.stderr)
        return 2
    snap = build(TestClient(app), get_engine())
    sample_run.SNAPSHOT.write_text(
        json.dumps(snap, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n = sum(len(q["items"]) for q in snap["questionnaires"].values())
    print(
        f"wrote data/dev/sample-run.json: {n} questionnaire items, {len(snap['gap']['items'])} gap outcomes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

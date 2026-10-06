"""The precomputed sample run (spec 5 step 4 and 9; Plan 4 Task 3): "Try with a sample company" copies the
engine's answers for the bundled questionnaires and the core gap check from data/dev/sample-run.json instead
of calling a model, so the default path is instant and spends nothing. scripts/sample_snapshot.py writes the
file by replaying the eval recordings (evals/recorded/dev.jsonl and gap-dev.jsonl) through the real endpoints:
no key, no spend, and the demo shows what the committed eval results score. tests/test_sample_run.py
regenerates it in CI and fails on any difference. At run time a digest of the inputs that can change a copied
answer is compared with the deployed ones; a stale snapshot is never copied: the run goes live."""

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import csf
from app.api.documents import SAMPLE_DIR as DOCS
from app.api.documents import SAMPLE_ORDER
from app.db.models import Answer, Chunk, Document, Item, Questionnaire, Run, RunItem
from app.draft import PROMPT_VERSION as DRAFT_PROMPT
from app.questionnaires import SAMPLE_DIR as QDIR
from app.services import audit_log
from app.settings import reasoning_for
from app.stance import PROMPT_VERSION as STANCE_PROMPT

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "dev" / "sample-run.json"
QUESTIONNAIRES = ("vsq-a.xlsx", "mvsp-b.csv")
STEPS = ("stance", "draft")  # the steps a fill run calls; the sample load classifies by rules alone
ANSWER_FIELDS = (
    "label",
    "value",
    "text",
    "citations",
    "dropped",
    "conflict",
    "scope_note",
    "confidence",
    "stances",
    "chunk_ids",
    "retrieval_dropped",
)
ENABLED = True  # scripts/sample_snapshot.py turns copying off while it writes a new snapshot


@cache
def _digest(models_key: tuple[tuple[str, str], ...]) -> str:
    h = hashlib.sha256()
    for name in SAMPLE_ORDER:
        h.update(name.encode() + b"\0" + (DOCS / name).read_bytes())
    for name in QUESTIONNAIRES:
        h.update(name.encode() + b"\0" + (QDIR / name).read_bytes())
    models = dict(models_key)
    meta = {
        "prompts": [STANCE_PROMPT, DRAFT_PROMPT],
        "models": models,
        "reasoning": {step: reasoning_for(step, models[step]) for step in STEPS},
        "csf": csf.current_mapping("core"),
    }
    h.update(json.dumps(meta, sort_keys=True).encode())
    return h.hexdigest()[:16]


def digest(models: Mapping[str, str]) -> str:
    """What the snapshot's answers depend on and the CI regeneration test cannot see in production: the sample
    documents and questionnaires, the stance and draft prompts, models and reasoning, the core CSF mapping."""
    return _digest(tuple((step, models[step]) for step in STEPS))


@cache
def snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT.exists():
        return None
    loaded: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return loaded


def _current(models: Mapping[str, str]) -> dict[str, Any] | None:
    snap = snapshot() if ENABLED else None
    return snap if snap is not None and snap["digest"] == digest(models) else None


def ready(models: Mapping[str, str]) -> bool:
    """The deployed inputs match the snapshot, so the sample path is copied (GET /api/version, the smoke
    test)."""
    return _current(models) is not None


def swap(values: Any, chunk: Callable[[str], str], doc: Callable[[str], str]) -> Any:
    """Every `chunk_id`, `document_id` and `chunk_ids` in a nested answer value, rewritten by `chunk` and
    `doc`. The snapshot names a chunk "<file name>#<line start>" and a document by its file name; a workspace
    holds its own ids. A name `chunk` or `doc` does not know raises KeyError."""
    if isinstance(values, list):
        return [swap(v, chunk, doc) for v in values]
    if not isinstance(values, dict):
        return values
    out = {k: swap(v, chunk, doc) for k, v in values.items()}
    if isinstance(out.get("chunk_id"), str):
        out["chunk_id"] = chunk(out["chunk_id"])
    if isinstance(out.get("document_id"), str):
        out["document_id"] = doc(out["document_id"])
    if isinstance(out.get("chunk_ids"), list):
        out["chunk_ids"] = [chunk(c) for c in out["chunk_ids"]]
    return out


def starts(rows: Any) -> dict[str, list[int]]:
    """Each document's chunk line starts, sorted, from (chunk id, line start, document id, file name) rows."""
    out: dict[str, list[int]] = {}
    for _, line, _, name in rows:
        out.setdefault(name, []).append(line)
    return {name: sorted(lines) for name, lines in out.items()}


def _sample_pack_only(session: Session, workspace_id: uuid.UUID) -> bool:
    """The workspace holds the sample pack and nothing else, with no metadata changed: only then do the
    snapshot's answers describe it (an upload, an answer to a question or an override changes what the engine
    would say)."""
    docs = session.execute(
        select(Document.filename, Document.source, Document.metadata_source).where(
            Document.workspace_id == workspace_id
        )
    ).all()
    return sorted(d.filename for d in docs) == sorted(SAMPLE_ORDER) and all(
        d.source == "sample" and d.metadata_source == "rule" for d in docs
    )


def _copy(
    session: Session,
    workspace_id: uuid.UUID,
    q: Questionnaire,
    pairs: list[tuple[Item, dict[str, Any]]],
    snap: dict[str, Any],
    models: Mapping[str, str],
) -> Run | None:
    rows = session.execute(
        select(Chunk.id, Chunk.line_start, Document.id, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.workspace_id == workspace_id)
    ).all()
    # adversary-1 M7 (review m3): a workspace chunked by an older deploy can hold the same "<file>#<line>"
    # names over other boundaries; only the chunking the snapshot was built on (every chunk's line start) is
    # copied
    if starts(rows) != snap["chunks"]:
        return None
    chunks = {f"{name}#{line}": str(cid) for cid, line, _, name in rows}
    docs = {name: str(did) for _, _, did, name in rows}
    try:
        local = [
            (
                item,
                swap(e["values"], chunks.__getitem__, docs.__getitem__),
                swap(e.get("parts", {}), chunks.__getitem__, docs.__getitem__),
            )
            for item, e in pairs
        ]
    except KeyError:  # a chunk the snapshot cites is not in this workspace: never copy a dangling citation
        return None
    run = Run(
        workspace_id=workspace_id,
        questionnaire_id=q.id,
        status="done",
        finished_at=datetime.now(UTC),
        prompt_versions=snap["prompt_versions"],
        models={**dict(models), "snapshot": snap["digest"]},
    )
    session.add(run)
    session.flush()
    for item, values, parts in local:
        session.add(RunItem(run_id=run.id, item_id=item.id, state="done", parts=parts))
        session.add(Answer(workspace_id=workspace_id, run_id=run.id, item_id=item.id, **values))
    audit_log.record(
        session,
        workspace_id,
        "run.create",
        ref=str(run.id),
        detail={"items": len(local), "precomputed": True},
    )
    session.commit()
    return run


def copy_questionnaire_run(
    session: Session, workspace_id: uuid.UUID, questionnaire_id: uuid.UUID, models: Mapping[str, str]
) -> Run | None:
    """A bundled sample questionnaire's run, copied; None when anything differs from the snapshot's world."""
    snap = _current(models)
    if snap is None:
        return None
    mine = (Questionnaire.id == questionnaire_id, Questionnaire.workspace_id == workspace_id)
    q = session.scalar(select(Questionnaire).where(*mine))
    if q is None or q.source != "sample" or q.filename not in snap["questionnaires"]:
        return None  # review m2: only a candidate copy takes the lock below
    # Locked like start_gap locks it, so two presses at once make one copy (M6)
    session.execute(select(Questionnaire.id).where(*mine).with_for_update())
    if not _sample_pack_only(session, workspace_id):
        return None
    copied = session.scalar(  # adversary-1 M6: a second press reloads the current copy
        select(Run)
        .where(
            Run.questionnaire_id == q.id,
            Run.status == "done",
            Run.models["snapshot"].astext == snap["digest"],
        )
        .order_by(Run.started_at.desc(), Run.id)
        .limit(1)
    )
    if copied is not None:
        return copied
    items = list(session.scalars(select(Item).where(Item.questionnaire_id == q.id).order_by(Item.position)))
    want = snap["questionnaires"][q.filename]["items"]
    if [(i.position, i.question, i.topic) for i in items] != [
        (e["position"], e["question"], e["topic"]) for e in want
    ]:
        return None
    return _copy(session, workspace_id, q, list(zip(items, want, strict=True)), snap, models)


def copy_gap_run(
    session: Session, workspace_id: uuid.UUID, q: Questionnaire, models: Mapping[str, str]
) -> Run | None:
    """The core gap check's run, copied; None for another scope or anything that differs."""
    snap = _current(models)
    if (
        snap is None
        or (q.mapping or {}).get("scope") != "core"
        or not _sample_pack_only(session, workspace_id)
    ):
        return None
    items = {i.csf_id: i for i in session.scalars(select(Item).where(Item.questionnaire_id == q.id))}
    want = snap["gap"]["items"]
    if sorted(str(k) for k in items) != sorted(e["csf_id"] for e in want):
        return None
    return _copy(session, workspace_id, q, [(items[e["csf_id"]], e) for e in want], snap, models)

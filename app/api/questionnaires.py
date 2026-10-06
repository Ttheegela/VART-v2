"""Questionnaires: import, the column mapper, samples (spec 5 step 2, 6.10). Owner: lane 3A-inputs (Task 5);
POST .../runs belongs to lane 3A-runs and lives in app/api/runs.py.

A questionnaire with source `csf` is built in (Plan 6B): it does not count toward MAX_QUESTIONNAIRES, and
the list and delete endpoints leave it out. The file's bytes are stored (xlsx and csv alike: export writes
back into the original rows). The sheet names, the format and the preview are cached in `mapping` at
upload and at confirm, so a GET never parses the file again."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from sqlalchemy import delete, exists, func, insert, select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep, WorkspaceDep
from app.api.documents import require_upload_allowance
from app.api.errors import GONE, Conflict, NotFound
from app.api.schemas import (
    ERRORS,
    MAX_QUESTIONNAIRE_BYTES,
    MAX_QUESTIONNAIRES,
    SENTENCE_422,
    ItemOut,
    Mapping,
    PreviewRow,
    QuestionnaireDetail,
    QuestionnaireOut,
)
from app.db.models import Item, Questionnaire, Run, Workspace
from app.ingest.parse import IngestError
from app.questionnaires import SAMPLE_DIR, SAMPLES, Sheet, detect, preview, read_items, read_sheets
from app.services import audit_log

router = APIRouter(tags=["questionnaires"], responses=ERRORS)

SHEET_NAME_MAX = 31  # Mapping.sheet's bound: a longer name could never be mapped


def _out(session: Session, q: Questionnaire, *, detail: bool = False) -> QuestionnaireOut:
    raw: dict[str, Any] = q.mapping or {}
    run = session.scalar(
        select(Run.id).where(Run.questionnaire_id == q.id).order_by(Run.started_at.desc()).limit(1)
    )
    items = list(session.scalars(select(Item).where(Item.questionnaire_id == q.id).order_by(Item.position)))
    fields: dict[str, Any] = {
        "id": q.id,
        "filename": q.filename,
        "source": q.source,
        "format": raw.get("format", "builtin"),
        "sheets": raw.get("sheets", []),
        "detected": raw.get("detected"),
        "mapping": raw.get("confirmed"),
        "preview": raw.get("preview", []),
        "item_count": len(items),
        "latest_run_id": run,
        "created_at": q.created_at,
    }
    if detail:
        return QuestionnaireDetail(**fields, items=[ItemOut.model_validate(i) for i in items])
    return QuestionnaireOut(**fields)


def _own(
    session: Session, ws: WorkspaceDep, questionnaire_id: uuid.UUID, *, lock: bool = False
) -> Questionnaire:
    stmt = select(Questionnaire).where(
        Questionnaire.id == questionnaire_id, Questionnaire.workspace_id == ws.id
    )
    q = session.scalar(stmt.with_for_update() if lock else stmt)  # the lock waits out a run being inserted
    if q is None:
        raise NotFound()
    return q


def _lock_workspace(session: Session, ws_id: uuid.UUID) -> None:
    if session.scalar(select(Workspace.id).where(Workspace.id == ws_id).with_for_update()) is None:
        raise HTTPException(404, GONE)


def _own_count(session: Session, ws_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Questionnaire)
            .where(Questionnaire.workspace_id == ws_id, Questionnaire.source != "csf")
        )
        or 0
    )


def _cache(sheets: list[Sheet], mapping: Mapping | None) -> list[dict[str, Any]]:
    rows: list[PreviewRow] = preview(sheets, mapping) if mapping else []
    return [r.model_dump() for r in rows]


def _itemise(session: Session, q: Questionnaire, mapping: Mapping) -> None:
    fmt, sheets = read_sheets(q.filename, q.original_bytes or b"")
    items = read_items(sheets, mapping)
    if not items:
        raise IngestError("This mapping finds no questions; pick the column that holds them.")
    session.execute(delete(Item).where(Item.questionnaire_id == q.id))
    session.execute(
        insert(Item),
        [
            {
                "workspace_id": q.workspace_id,
                "questionnaire_id": q.id,
                "position": n,
                "row_ref": f"{mapping.sheet + '!' if mapping.sheet else ''}{mapping.question_col}{i.row}",
                "code": i.code[:64] if i.code else None,
                "topic": i.topic,
                "question": i.question,
            }
            for n, i in enumerate(items, 1)
        ],
    )
    raw = dict(q.mapping or {})
    raw["confirmed"] = mapping.model_dump()
    raw["preview"] = _cache(sheets, mapping)
    q.sheet = mapping.sheet
    q.mapping = raw  # a new dict: JSONB change tracking is by assignment


def _new(
    ws_id: uuid.UUID,
    filename: str,
    source: str,
    data: bytes,
    fmt: str,
    sheets: list[Sheet],
    detected: Mapping | None,
) -> Questionnaire:
    return Questionnaire(
        workspace_id=ws_id,
        filename=filename,
        source=source,
        original_bytes=data,
        mapping={
            "format": fmt,
            "sheets": [s.name for s in sheets if s.name],
            "detected": detected.model_dump() if detected else None,
            "confirmed": None,
            "preview": _cache(sheets, detected),
        },
    )


@router.get("/api/questionnaires")
def list_questionnaires(ws: WorkspaceDep, session: SessionDep) -> list[QuestionnaireOut]:
    """The workspace's uploaded and sample questionnaires, newest first. The built-in `csf` one (Plan 6B) is
    left out: it is not the visitor's file and does not count toward the 5-per-workspace cap."""
    rows = session.scalars(
        select(Questionnaire)
        .where(Questionnaire.workspace_id == ws.id, Questionnaire.source != "csf")
        .order_by(Questionnaire.created_at.desc(), Questionnaire.id)
    )
    return [_out(session, q) for q in rows]


@router.post("/api/questionnaires", status_code=201, responses=SENTENCE_422)
def upload_questionnaire(
    ws: WorkspaceDep, session: SessionDep, request: Request, file: UploadFile
) -> QuestionnaireOut:
    """Multipart xlsx or csv. Answers the detected mapping and a preview; no items exist until the visitor
    confirms with PUT .../mapping. 422 for a refused file, a file over 1 MB (`MAX_QUESTIONNAIRE_BYTES`), or a
    workspace that already holds 5 questionnaires (`MAX_QUESTIONNAIRES`, built-in `csf` ones not counted);
    429 per network (`upload`); 503 when the demo is full. The sheet names are stored at upload, so listing
    never re-parses the file."""
    ws_id = ws.id
    require_upload_allowance(request, session)
    data = file.file.read(MAX_QUESTIONNAIRE_BYTES + 1)
    if len(data) > MAX_QUESTIONNAIRE_BYTES:
        raise IngestError("Questionnaire files must be 1 MB or smaller.")
    name = (file.filename or "questionnaire")[:255]
    fmt, sheets = read_sheets(name, data)
    if any(s.name and len(s.name) > SHEET_NAME_MAX for s in sheets):
        raise IngestError(
            f"A sheet name is longer than {SHEET_NAME_MAX} characters; shorten it and upload again."
        )
    _lock_workspace(session, ws_id)  # two uploads at once cannot both take the last slot
    if _own_count(session, ws_id) >= MAX_QUESTIONNAIRES:
        raise IngestError(f"A workspace holds at most {MAX_QUESTIONNAIRES} questionnaires; delete one first.")
    q = _new(ws_id, name, "upload", data, fmt, sheets, detect(sheets, fmt))
    session.add(q)
    session.flush()
    audit_log.record(session, ws_id, "questionnaire.upload", ref=str(q.id), detail={"format": fmt})
    session.commit()
    return _out(session, q)


@router.post("/api/questionnaires/sample/{name}", status_code=201, responses=SENTENCE_422)
def load_sample_questionnaire(
    name: str, ws: WorkspaceDep, session: SessionDep, request: Request
) -> QuestionnaireDetail:
    """`vsq-a` (xlsx) or `mvsp-b` (csv), mapped and itemised at once. 404 for another name. Idempotent:
    when the workspace already has that sample, it is answered again and nothing is stored. A new one counts
    under the per-network `upload` limit (429), the storage breaker (503) and `MAX_QUESTIONNAIRES` (422).
    No model call."""
    if name not in SAMPLES:
        raise NotFound()
    ws_id, filename = ws.id, SAMPLES[name]
    have = select(Questionnaire).where(
        Questionnaire.workspace_id == ws_id,
        Questionnaire.source == "sample",
        Questionnaire.filename == filename,
    )
    if (q := session.scalar(have)) is not None:
        return _out(session, q, detail=True)  # type: ignore[return-value]
    require_upload_allowance(request, session)  # commits: the lock comes after it
    _lock_workspace(session, ws_id)
    if (q := session.scalar(have)) is not None:  # a concurrent POST stored it while this one waited
        session.rollback()
        return _out(session, q, detail=True)  # type: ignore[return-value]
    if _own_count(session, ws_id) >= MAX_QUESTIONNAIRES:
        raise IngestError(f"A workspace holds at most {MAX_QUESTIONNAIRES} questionnaires; delete one first.")
    data = (SAMPLE_DIR / filename).read_bytes()
    fmt, sheets = read_sheets(filename, data)
    mapping = detect(sheets, fmt)
    assert mapping is not None  # pinned by test_the_samples_read_exactly_like_the_eval_items
    q = _new(ws_id, filename, "sample", data, fmt, sheets, mapping)
    session.add(q)
    session.flush()
    _itemise(session, q, mapping)
    audit_log.record(session, ws_id, "questionnaire.sample", ref=str(q.id), detail={"name": name})
    session.commit()
    return _out(session, q, detail=True)  # type: ignore[return-value]


@router.put("/api/questionnaires/{questionnaire_id}/mapping", responses=SENTENCE_422)
def confirm_mapping(
    questionnaire_id: uuid.UUID, mapping: Mapping, ws: WorkspaceDep, session: SessionDep
) -> QuestionnaireDetail:
    """Replace the items with the ones this mapping reads. 422 when it finds none or more than 150; 409 once a
    run exists for the questionnaire, or for a built-in `csf` one (it has no file to map)."""
    q = _own(session, ws, questionnaire_id, lock=True)
    if q.source == "csf":
        raise Conflict("A built-in questionnaire has no file to map.")
    if session.scalar(select(exists().where(Run.questionnaire_id == q.id))):
        raise Conflict("A run already used this mapping; upload the file again to map it differently.")
    ws_id, q_id = ws.id, q.id
    _itemise(session, q, mapping)
    audit_log.record(session, ws_id, "questionnaire.mapping", ref=str(q_id), detail={"sheet": mapping.sheet})
    session.commit()
    return _out(session, q, detail=True)  # type: ignore[return-value]


@router.get("/api/questionnaires/{questionnaire_id}")
def get_questionnaire(
    questionnaire_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep
) -> QuestionnaireDetail:
    return _out(session, _own(session, ws, questionnaire_id), detail=True)  # type: ignore[return-value]


@router.delete("/api/questionnaires/{questionnaire_id}", status_code=204)
def delete_questionnaire(questionnaire_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> None:
    """Remove a questionnaire and its items, so the 5-per-workspace cap does not force a reset. 409 when a
    run used it (reset the workspace to start over). A built-in `csf` questionnaire is 404 here. The row is
    locked before the run check, so a run being created at the same moment either wins (409) or fails."""
    q = _own(session, ws, questionnaire_id, lock=True)
    if q.source == "csf":
        raise NotFound()
    if session.scalar(select(exists().where(Run.questionnaire_id == q.id))):
        raise Conflict("A run used this questionnaire, so it stays; reset the workspace to start over.")
    ws_id, q_id = ws.id, q.id
    session.delete(q)
    audit_log.record(session, ws_id, "questionnaire.delete", ref=str(q_id))
    session.commit()

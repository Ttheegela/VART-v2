"""Documents (spec 5 step 3, 6.12). Owner: lane 3A-inputs (Task 4)."""

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from app.api.deps import LLMDep, SessionDep, WorkspaceDep
from app.api.errors import GONE, Conflict, NotFound, limit, network
from app.api.schemas import (
    ERRORS,
    MAX_LINES_PER_READ,
    SENTENCE_422,
    DocumentOut,
    DocumentPatch,
    DocumentUpdated,
    LineOut,
    LinesOut,
)
from app.classify import classify
from app.db.models import (
    Answer,
    Chunk,
    Document,
    DocumentLine,
    InterviewQuestion,
    Run,
    SuggestedFill,
    Workspace,
)
from app.ingest.parse import MAX_BYTES, MAX_LINES, IngestError, parse
from app.ingest.store import _store, ingest_document
from app.redecide import redecide
from app.services import audit_log
from app.services.capacity import ensure_capacity
from app.services.llm_budget import spender
from app.settings import get_settings

router = APIRouter(tags=["documents"], responses=ERRORS)

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dev" / "docs"
# The fact sheet's order (data/dev/facts.yaml), never a glob (Plan 2 addendum): the dev recordings assume it.
SAMPLE_ORDER = (  # pinned by tests/test_api_documents.py::test_the_sample_pack_loads_once_in_fact_sheet_order
    "information-security-policy.docx",
    "access-control-policy.docx",
    "data-classification-policy.md",
    "cryptography-policy.docx",
    "vulnerability-management-policy.docx",
    "incident-response-policy-DRAFT.docx",
    "business-continuity-policy.md",
    "vendor-risk-management-policy.docx",
    "hr-security-policy.docx",
    "secure-development-policy.md",
    "asset-management-policy.docx",
    "logging-and-monitoring-policy.docx",
    "soc2-type-ii-report-summary.pdf",
    "penetration-test-report-2026.pdf",
    "access-review-records.xlsx",
    "asset-inventory.xlsx",
    "bcp-dr-plan.docx",
    "master-services-agreement-template.docx",
    "employee-handbook-DRAFT.docx",
    "security-policy-template.md",
    "engineering-wiki-export.md",
    "security-faq.md",
)


def document_out(d: Document) -> DocumentOut:
    return DocumentOut.model_validate(d)


def require_upload_allowance(request: Request, session: Session) -> None:
    """Per-network `upload` limit, then the storage breaker (Task 5 calls this too)."""
    limit(request, session, "upload")
    ensure_capacity(session)


def _own(session: Session, ws: Workspace, document_id: uuid.UUID) -> Document:
    doc = session.scalar(select(Document).where(Document.id == document_id, Document.workspace_id == ws.id))
    if doc is None:
        raise NotFound()
    return doc


@router.get("/api/documents")
def list_documents(ws: WorkspaceDep, session: SessionDep) -> list[DocumentOut]:
    """Every document in the workspace, sample, uploaded and statements, oldest first."""
    rows = session.scalars(
        select(Document).where(Document.workspace_id == ws.id).order_by(Document.created_at, Document.id)
    )
    return [document_out(d) for d in rows]


@router.post("/api/documents", status_code=201, responses=SENTENCE_422)
def upload_document(
    ws: WorkspaceDep, session: SessionDep, request: Request, llm: LLMDep, file: UploadFile
) -> DocumentOut:
    """Multipart upload of one file. Parsed in memory, redacted, classified, chunked; the bytes are not
    stored. 422 with a sentence for a refused file; 429 per network (`upload`, 60 an hour); 503 when full.
    A body over Vercel's 4.5 MB limit gets the platform's own 413 (not JSON) before the app sees it."""
    ws_id = ws.id
    require_upload_allowance(request, session)
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise IngestError("Files must be 4 MB or smaller.")
    doc = ingest_document(
        session,
        ws_id,
        file.filename or "upload",
        data,
        source="upload",
        llm=llm,
        model=get_settings().models()["classify"],
        spend=spender(session, ws_id, network(request)),
    )
    audit_log.record(session, ws_id, "document.upload", ref=str(doc.id), detail={"kind": doc.kind})
    session.commit()
    return document_out(doc)


@router.post("/api/documents/sample", status_code=201)
def load_sample_documents(ws: WorkspaceDep, session: SessionDep) -> list[DocumentOut]:
    """The sample company's documents (not redacted, not counted against the upload limit). Idempotent."""
    ws_id = ws.id
    loaded = 0
    for name in SAMPLE_ORDER:  # rules classify all 22 (plan2b Task 3): no model call, no budget
        # Pre-flight P19: lock the workspace row, re-check, insert in one transaction; ingest_document
        # commits before it stores a sample (dropping the lock), so its steps run here.
        if session.scalar(select(Workspace.id).where(Workspace.id == ws_id).with_for_update()) is None:
            raise HTTPException(404, GONE)
        have = session.scalar(
            select(
                exists().where(
                    Document.workspace_id == ws_id, Document.source == "sample", Document.filename == name
                )
            )
        )
        if have:
            session.rollback()
            continue
        if loaded == 0:
            ensure_capacity(session)
        data = (SAMPLE_DIR / name).read_bytes()
        parsed = parse(name, data)
        meta = classify(name, parsed, None, "", lambda step: False)
        _store(session, ws_id, name, "sample", hashlib.sha256(data).hexdigest(), meta, parsed.lines)
        loaded += 1
    if loaded:
        audit_log.record(session, ws_id, "document.sample", detail={"documents": loaded})
    session.commit()
    rows = session.scalars(
        select(Document)
        .where(Document.workspace_id == ws_id, Document.source == "sample")
        .order_by(Document.created_at, Document.id)
    )
    return [document_out(d) for d in rows]


@router.patch("/api/documents/{document_id}")
def update_document(
    document_id: uuid.UUID, patch: DocumentPatch, ws: WorkspaceDep, session: SessionDep
) -> DocumentUpdated:
    """Override metadata; every answer that used this document is decided again with no model call."""
    doc = _own(session, ws, document_id)  # an empty patch changes nothing, not even metadata_source
    changes = patch.model_dump(exclude_unset=True)
    ws_id, doc_id = ws.id, doc.id
    if not changes:
        return DocumentUpdated(**document_out(doc).model_dump(), redecided=0)
    for field, value in changes.items():
        setattr(doc, field, value)
    doc.metadata_source = "user"
    audit_log.record(session, ws_id, "document.update", ref=str(doc_id), detail={"fields": sorted(changes)})
    session.commit()
    n = redecide(session, ws_id, doc_id)
    return DocumentUpdated(**document_out(doc).model_dump(), redecided=n)


@router.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> None:
    """409 while a run is going (a step may be citing the document) and when a run used the document (reset
    the workspace to start over)."""
    doc = _own(session, ws, document_id)
    # a run's insert takes a key-share lock on the workspace row (its foreign key), so this row lock waits for
    # a run being created and keeps a new one from starting between the check and the delete (final review M8)
    if session.scalar(select(Workspace.id).where(Workspace.id == ws.id).with_for_update()) is None:
        raise HTTPException(404, GONE)
    if session.scalar(select(exists().where(Run.workspace_id == ws.id, Run.status == "running"))):
        raise Conflict("A run is in progress; wait for it to finish.")
    chunk_ids = [str(c) for c in session.scalars(select(Chunk.id).where(Chunk.document_id == doc.id))]
    used = session.scalar(
        select(
            exists().where(
                Answer.workspace_id == ws.id,
                (Answer.statement_id == doc.id) | Answer.chunk_ids.has_any(array(chunk_ids or [""])),
            )
            | exists().where(SuggestedFill.statement_id == doc.id)  # pre-flight P20: NO ACTION foreign keys
            | exists().where(InterviewQuestion.statement_id == doc.id)
        )
    )
    if used:
        raise Conflict("A run used this document, so it stays; reset the workspace to start over.")
    ws_id, doc_id = ws.id, doc.id
    session.delete(doc)
    audit_log.record(session, ws_id, "document.delete", ref=str(doc_id))
    session.commit()


@router.get("/api/documents/{document_id}/lines", responses=SENTENCE_422)
def document_lines(
    document_id: uuid.UUID,
    ws: WorkspaceDep,
    session: SessionDep,
    start: Annotated[int, Query(alias="from", ge=1, le=MAX_LINES)] = 1,
    end: Annotated[int | None, Query(alias="to", ge=1, le=MAX_LINES)] = None,
) -> LinesOut:
    """Stored (redacted) lines `from`..`to`, at most 200."""
    doc = _own(session, ws, document_id)
    end = end if end is not None else start + MAX_LINES_PER_READ - 1
    if end < start or end - start + 1 > MAX_LINES_PER_READ:
        raise HTTPException(422, f"Ask for at most {MAX_LINES_PER_READ} lines at a time.")
    rows = session.execute(
        select(DocumentLine.n, DocumentLine.text)
        .where(DocumentLine.document_id == doc.id, DocumentLine.n.between(start, end))
        .order_by(DocumentLine.n)
    )
    return LinesOut(document_id=doc.id, filename=doc.filename, lines=[LineOut(n=n, text=t) for n, t in rows])

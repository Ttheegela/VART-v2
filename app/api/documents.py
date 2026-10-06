"""Documents (spec 5 step 3, 6.12). Owner: lane 3A-inputs (Task 4)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, UploadFile

from app.api.deps import LLMDep, SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import ERRORS, SENTENCE_422, DocumentOut, DocumentPatch, DocumentUpdated, LinesOut

router = APIRouter(tags=["documents"], responses=ERRORS)


@router.get("/api/documents")
def list_documents(ws: WorkspaceDep, session: SessionDep) -> list[DocumentOut]:
    """Every document in the workspace, sample, uploaded and statements, oldest first."""
    raise not_built()


@router.post("/api/documents", status_code=201, responses=SENTENCE_422)
def upload_document(
    ws: WorkspaceDep, session: SessionDep, request: Request, llm: LLMDep, file: UploadFile
) -> DocumentOut:
    """Multipart upload of one file. Parsed in memory, redacted, classified, chunked; the bytes are not
    stored. 422 with a sentence for a refused file; 429 per network (`upload`, 60 an hour); 503 when full.
    A body over Vercel's 4.5 MB limit gets the platform's own 413 (not JSON) before the app sees it."""
    raise not_built()


@router.post("/api/documents/sample", status_code=201)
def load_sample_documents(ws: WorkspaceDep, session: SessionDep) -> list[DocumentOut]:
    """The sample company's documents (not redacted, not counted against the upload limit). Idempotent."""
    raise not_built()


@router.patch("/api/documents/{document_id}")
def update_document(
    document_id: uuid.UUID, patch: DocumentPatch, ws: WorkspaceDep, session: SessionDep
) -> DocumentUpdated:
    """Override metadata; every answer that used this document is decided again with no model call."""
    raise not_built()


@router.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> None:
    """409 when a run used the document (reset the workspace to start over)."""
    raise not_built()


@router.get("/api/documents/{document_id}/lines", responses=SENTENCE_422)
def document_lines(
    document_id: uuid.UUID,
    ws: WorkspaceDep,
    session: SessionDep,
    start: Annotated[int, Query(alias="from", ge=1)] = 1,
    end: Annotated[int | None, Query(alias="to", ge=1)] = None,
) -> LinesOut:
    """Stored (redacted) lines `from`..`to`, at most 200."""
    raise not_built()

"""Ingest service (spec 6.4, 9): one file becomes a documents row, its numbered lines and its chunks, in one
transaction. Upload bytes are parsed in memory and never stored (only their sha256). Uploads and the
visitor's own answers are redacted before storage and before any model call; sample packs are not (Plan 1A
Ruling 10), and only sample packs may hold more than MAX_DOCUMENTS documents (the dev pack has 22, Plan 1B
Ruling 19)."""

import hashlib
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from typing import Literal

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.chunk import chunk_lines
from app.classify import classify
from app.contracts import DocMeta, Line, Spend
from app.db.models import Chunk, Document, DocumentLine, Workspace
from app.ingest.parse import IngestError, parse
from app.llm.client import LLMClient
from app.patterns import INJECTION
from app.redact import redact_lines, redact_text
from app.text import normalize

log = logging.getLogger(__name__)

MAX_DOCUMENTS = 20  # spec 9, per workspace (uploads and drive files only)
MAX_WORKSPACE_LINES = 20_000  # spec 9, per workspace


def _name_reads_like_an_instruction(filename: str) -> bool:
    """Separators (any non-letter) read as spaces; also tried with camelCase split, so "IgnoreAll..." and
    "IGNOREAll..." match, while "iGnOrE all ..." matches in the plain form."""
    name = normalize(filename)
    plain = re.sub(r"[\W\d_]+", " ", name)
    split = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return bool(INJECTION.search(plain) or INJECTION.search(re.sub(r"[\W\d_]+", " ", split)))


def _check_limits(session: Session, workspace_id: uuid.UUID, new_lines: int) -> None:
    docs, lines = session.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.line_count), 0)).where(
            Document.workspace_id == workspace_id, Document.source.in_(("upload", "drive"))
        )
    ).one()
    if docs >= MAX_DOCUMENTS:
        raise IngestError(f"A workspace can hold at most {MAX_DOCUMENTS} documents.")
    if lines + new_lines > MAX_WORKSPACE_LINES:
        raise IngestError(f"A workspace can hold at most {MAX_WORKSPACE_LINES:,} lines of text.")


def _store(
    session: Session,
    workspace_id: uuid.UUID,
    filename: str,
    source: str,
    sha256: str,
    meta: DocMeta,
    lines: Sequence[Line],
) -> Document:
    if source in ("upload", "drive"):
        # Lock the workspace row and count again: ingest_document committed its first check before classify
        # (and the spender commits too), so two uploads at once could otherwise both pass it.
        session.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
        _check_limits(session, workspace_id, len(lines))
    doc = Document(
        workspace_id=workspace_id,
        filename=filename[:255],
        source=source,
        sha256=sha256,
        kind=meta.kind,
        status=meta.status,
        effective_date=meta.effective_date,
        scope=meta.scope,
        evidence_allowed=meta.evidence_allowed,
        metadata_source=meta.source,
        line_count=len(lines),
    )
    session.add(doc)
    session.flush()
    session.execute(
        insert(DocumentLine),
        [{"document_id": doc.id, "n": n, "text": x.text} for n, x in enumerate(lines, 1)],
    )
    chunks = chunk_lines(lines)
    if chunks:
        session.execute(
            insert(Chunk),
            [
                {
                    "workspace_id": workspace_id,
                    "document_id": doc.id,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "text": c.text,
                    "heading": c.heading,
                    "flags": list(c.flags),
                    "as_of": c.as_of,
                    "record": c.record,
                }
                for c in chunks
            ],
        )
    session.commit()
    return doc


def ingest_document(
    session: Session,
    workspace_id: uuid.UUID,
    filename: str,
    data: bytes,
    *,
    source: Literal["sample", "upload", "drive"],
    llm: LLMClient | None,
    model: str,
    spend: Spend,
) -> Document:
    """Raises IngestError (shown to the visitor as is) for a file the app will not take."""
    # The name is printed in every model prompt. Read separators as spaces and split camelCase,
    # so "ignore.all.previous.instructions" and "IgnoreAllPrevious..." are caught like the spaced name.
    if source != "sample" and _name_reads_like_an_instruction(filename):
        raise IngestError("The file name reads like an instruction; rename the file.")
    try:
        parsed = parse(filename, data)
    except IngestError as exc:
        if exc.__cause__ is not None:  # parse's catch-all hides a parser bug as "damaged": keep the cause
            log.warning("ingest of %r refused: %s", redact_text(filename), exc, exc_info=exc.__cause__)
        raise
    if source != "sample":
        _check_limits(session, workspace_id, len(parsed.lines))
        parsed = replace(parsed, lines=redact_lines(parsed.lines))
        filename = redact_text(filename)
    session.commit()  # ends any open read: no transaction stays open across classify's model call
    meta = classify(filename, parsed, llm, model, spend)
    digest = hashlib.sha256(data).hexdigest()
    return _store(session, workspace_id, filename, source, digest, meta, parsed.lines)


def store_statement(
    session: Session, workspace_id: uuid.UUID, text: str, *, filename: str, today: date
) -> Document:
    """The visitor's accepted interview answer as a dated statement (spec 6.9): kind and source 'statement',
    evidence, dated `today`, redacted like an upload. One plain line per non-empty line, not Markdown: an
    answer such as "#1 priority: ..." is a statement, not a heading."""
    lines = redact_lines([Line(t) for p in text.splitlines() if (t := normalize(p))])
    if not lines:
        raise IngestError("The answer is empty.")
    meta = DocMeta("statement", "final", today, None, True, "rule")
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
    return _store(session, workspace_id, filename, "statement", digest, meta, lines)

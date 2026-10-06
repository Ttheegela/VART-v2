"""Answers (spec 5 steps 5 and 7). Owner: lane 3A-runs (Task 8)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import Conflict, NotFound
from app.api.runs import summary
from app.api.schemas import (
    ERRORS,
    AnswerDetail,
    AnswerEdit,
    AnswerSummary,
    CitationOut,
    ConflictOut,
    ConflictSideOut,
    ContextLine,
    DroppedOut,
    ItemOut,
    LineOut,
    NotApplicableIn,
)
from app.db.models import Answer, Chunk, Document, DocumentLine, Item
from app.redact import redact_text
from app.services import audit_log
from app.text import contains

router = APIRouter(tags=["answers"], responses=ERRORS)
CONTEXT = 2  # lines each side of a cited line
WHY = {
    "containment": "The quoted words are not in this line, so the quote was not used.",
    "quote-length": "The quote was shorter than 3 or longer than 30 words.",
    "record-field": "The quote did not copy whole fields of this spreadsheet row.",
    "not-evidence": "This document does not count as evidence (a contract, template or questionnaire).",
    "placeholder": "This passage is unfilled template text.",
    "injection": "This passage contains instructions aimed at a model, so it was never sent to one.",
}


def _own(session: SessionDep, ws: WorkspaceDep, answer_id: uuid.UUID, *, lock: bool = False) -> Answer:
    """lock: for a write, so an edit, an approval and a not-applicable on one answer take turns."""
    query = select(Answer).where(Answer.id == answer_id, Answer.workspace_id == ws.id)
    a = session.scalar(query.with_for_update() if lock else query)
    if a is None:
        raise NotFound()
    return a


def _lines(session: SessionDep, document_id: uuid.UUID, start: int, end: int) -> list[tuple[int, str]]:
    return list(
        session.execute(
            select(DocumentLine.n, DocumentLine.text)
            .where(DocumentLine.document_id == document_id, DocumentLine.n.between(start, end))
            .order_by(DocumentLine.n)
        ).tuples()
    )


def _citation(session: SessionDep, c: dict) -> CitationOut:  # type: ignore[type-arg]
    doc = session.get_one(Document, uuid.UUID(c["document_id"]))
    as_of = session.scalar(select(Chunk.as_of).where(Chunk.id == uuid.UUID(c["chunk_id"])))
    lines = _lines(session, doc.id, max(1, c["line_start"] - CONTEXT), c["line_end"] + CONTEXT)
    cited = {n: t for n, t in lines if c["line_start"] <= n <= c["line_end"]}
    return CitationOut(
        document_id=doc.id,
        filename=doc.filename,
        kind=doc.kind,
        status=doc.status,
        date=as_of or doc.effective_date,
        scope=doc.scope,
        line=c["line_start"],
        quote=c["quote"],
        stance=c["stance"],
        found_in_source=any(contains(t, c["quote"]) for t in cited.values()),
        context=[ContextLine(n=n, text=t, cited=n in cited) for n, t in lines],
    )


def detail(session: SessionDep, a: Answer) -> AnswerDetail:
    citations = [_citation(session, c) for c in a.citations]
    index = {(c["chunk_id"], c["quote"]): i for i, c in enumerate(a.citations)}
    conflict = None
    if a.conflict:
        conflict = ConflictOut(
            rule=a.conflict["rule"],
            sides=[
                ConflictSideOut(
                    stance=side["stance"],
                    date=side["date"],
                    citations=[
                        index[(c["chunk_id"], c["quote"])]
                        for c in side["citations"]
                        if (c["chunk_id"], c["quote"]) in index
                    ],
                )
                for side in a.conflict["sides"]
            ],
        )
    dropped = []
    for d in a.dropped:
        line = session.scalar(select(Chunk.line_start).where(Chunk.id == uuid.UUID(d["chunk_id"])))
        dropped.append(
            DroppedOut(
                reason=d["reason"],
                document_id=uuid.UUID(d["document_id"]),
                filename=d["filename"],
                line=line,
                sentence=WHY[d["reason"]],
            )
        )
    statement = (
        [LineOut(n=n, text=t) for n, t in _lines(session, a.statement_id, 1, 200)] if a.statement_id else []
    )
    item = session.get_one(Item, a.item_id)
    return AnswerDetail(
        **summary(a).model_dump(),
        item=ItemOut.model_validate(item),
        citations=citations,
        dropped=dropped,
        conflict=conflict,
        scope_note=a.scope_note,
        statement_lines=statement,
    )


@router.get("/api/answers/{answer_id}")
def get_answer(answer_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerDetail:
    """The Evidence drawer: citations re-read from the stored lines with context, dropped evidence, both
    sides of a conflict, the scope note, the visitor's statement."""
    return detail(session, _own(session, ws, answer_id))


@router.patch("/api/answers/{answer_id}")
def edit_answer(
    answer_id: uuid.UUID, edit: AnswerEdit, ws: WorkspaceDep, session: SessionDep
) -> AnswerSummary:
    """Edit the text; the answer becomes unapproved and `edited`."""
    a = _own(session, ws, answer_id, lock=True)
    a.text, a.edited, a.approved_at = edit.text, True, None
    audit_log.record(session, ws.id, "answer.edit", ref=str(a.id))
    session.commit()
    return summary(a)


@router.post("/api/answers/{answer_id}/approve")
def approve_answer(answer_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerSummary:
    """409 for a conflict or an unknown answer (answer the question first)."""
    a = _own(session, ws, answer_id, lock=True)
    if a.label == "conflict":
        raise Conflict("Resolve the conflict first: answer the question for this item.")
    if a.label == "unknown":
        raise Conflict("Answer the question for this item first.")
    a.approved_at = datetime.now(UTC)
    audit_log.record(session, ws.id, "answer.approve", ref=str(a.id))
    session.commit()
    return summary(a)


@router.post("/api/answers/{answer_id}/not-applicable")
def mark_not_applicable(
    answer_id: uuid.UUID, body: NotApplicableIn, ws: WorkspaceDep, session: SessionDep
) -> AnswerSummary:
    """Label `na` with the reason in the audit log (spec 6.9)."""
    a = _own(session, ws, answer_id, lock=True)
    reason = redact_text(body.reason)
    a.label, a.value, a.text, a.approved_at = "na", None, f"Not applicable: {reason}", None
    # the engine's evidence no longer describes this answer (pre-flight P7, adversary-1 M6)
    a.citations, a.dropped, a.conflict, a.scope_note, a.statement_id = [], [], None, None, None
    a.stances, a.chunk_ids, a.retrieval_dropped = [], [], []
    audit_log.record(session, ws.id, "answer.not_applicable", ref=str(a.id), detail={"reason": reason})
    session.commit()
    return summary(a)

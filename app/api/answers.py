"""Answers (spec 5 steps 5 and 7). Owner: lane 3A-runs (Task 8)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import csf
from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import Conflict, NotFound, limit
from app.api.runs import summary
from app.api.schemas import (
    ERRORS,
    SENTENCE_422,
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
    PartOut,
)
from app.db.models import Answer, Chunk, Document, DocumentLine, Item, RunItem
from app.ingest.store import store_statement
from app.questions import lock_workspace, statement_filename
from app.redact import redact_text
from app.runs import FAILED_TEXT
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
    "statement": "This is your own answer; a CSF outcome is judged on documents only.",
}


def _own(session: SessionDep, ws: WorkspaceDep, answer_id: uuid.UUID, *, lock: bool = False) -> Answer:
    """lock: for a write, so an edit, an approval and a not-applicable on one answer take turns."""
    query = select(Answer).where(Answer.id == answer_id, Answer.workspace_id == ws.id)
    a = session.scalar(query.with_for_update() if lock else query)
    if a is None:
        raise NotFound()
    return a


def _not_gap(session: SessionDep, a: Answer) -> None:
    """A gap check's outcome is code's finding: an edit would reach the sheet as code's words, and an edit or
    an approval would keep Check again off it (adversary-2 M5). Its labels change only through the gap view
    (Check again, Ask me, a fill, not applicable)."""
    if session.scalar(select(Item.csf_id).where(Item.id == a.item_id)) is not None:
        raise Conflict(
            "A gap check's outcome is not edited or approved; press r in the gap check to check it again."
        )


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


def _dropped(session: SessionDep, d: dict) -> DroppedOut:  # type: ignore[type-arg]
    line = session.scalar(select(Chunk.line_start).where(Chunk.id == uuid.UUID(d["chunk_id"])))
    return DroppedOut(
        reason=d["reason"],
        document_id=uuid.UUID(d["document_id"]),
        filename=d["filename"],
        line=line,
        sentence=WHY[d["reason"]],
    )


def _parts(session: SessionDep, a: Answer, item: Item) -> list[PartOut]:
    """A Checked CSF outcome's parts as the runner stored them (CSF spec 5.2, carry d); [] for anything else,
    and for an outcome whose parts are not all stored, or that failed or was marked not applicable: a cited
    document may be gone by then (adversary-1 M2, preflight M2)."""
    o = csf.outcome_or_none(item.csf_id) if item.csf_id else None
    if o is None or o.tier != "checked" or a.label == "na" or a.text == FAILED_TEXT:
        return []
    stored = (
        session.scalar(select(RunItem.parts).where(RunItem.run_id == a.run_id, RunItem.item_id == a.item_id))
        or {}
    )
    if len(stored) != len(o.parts):
        return []
    return [
        PartOut(
            n=int(k),
            question=raw["question"],
            label=csf.part_label(csf.part_result(o, int(k), raw)),
            citations=[_citation(session, c) for c in raw["citations"]],
            dropped=[_dropped(session, d) for d in raw["dropped"]],
            from_statement=raw.get("statement_id") is not None,
        )
        for k, raw in sorted(stored.items(), key=lambda kv: int(kv[0]))
    ]


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
    dropped = [_dropped(session, d) for d in a.dropped]
    item = session.get_one(Item, a.item_id)
    statement = (
        [LineOut(n=n, text=t) for n, t in _lines(session, a.statement_id, 1, 200)] if a.statement_id else []
    )
    return AnswerDetail(
        **summary(a).model_dump(),
        item=ItemOut.model_validate(item),
        citations=citations,
        dropped=dropped,
        conflict=conflict,
        scope_note=a.scope_note,
        statement_lines=statement,
        parts=_parts(session, a, item),
    )


@router.get("/api/answers/{answer_id}")
def get_answer(answer_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerDetail:
    """The Evidence drawer: citations re-read from the stored lines with context, dropped evidence, both
    sides of a conflict, the scope note, the visitor's statement."""
    return detail(session, _own(session, ws, answer_id))


@router.patch("/api/answers/{answer_id}", responses=SENTENCE_422)
def edit_answer(
    answer_id: uuid.UUID, edit: AnswerEdit, ws: WorkspaceDep, session: SessionDep, request: Request
) -> AnswerSummary:
    """Edit the text; the answer becomes unapproved and `edited`. On a Confirmed-by-you answer the edit is the
    visitor's new answer: it is stored as a new dated, redacted statement and the answer points to it
    (Plan 3 M6), counted under the network's `interview` cap (each pays for redaction, adversary-1 N2).
    409 for a gap check's outcome; 422 when the redacted answer is empty or too long."""
    ws_id = ws.id
    label = session.scalar(select(Answer.label).where(Answer.id == answer_id, Answer.workspace_id == ws_id))
    if label == "user_confirmed":
        limit(request, session, "interview")  # commits: before any lock
    lock_workspace(session, ws_id)  # first, as every write that stores a statement (Plan 4 Task 5)
    a = _own(session, ws, answer_id, lock=True)
    _not_gap(session, a)
    text = edit.text
    if a.label == "user_confirmed":
        position = session.scalar(select(Item.position).where(Item.id == a.item_id)) or 0
        said = store_statement(
            session,
            ws_id,
            text,
            filename=statement_filename(position),
            today=datetime.now(UTC).date(),
            commit=False,
        )
        lines = session.scalars(
            select(DocumentLine.text).where(DocumentLine.document_id == said.id).order_by(DocumentLine.n)
        )
        a.statement_id, text = said.id, " ".join(lines)
    a.text, a.edited, a.approved_at = text, True, None
    audit_log.record(session, ws_id, "answer.edit", ref=str(a.id))
    session.commit()
    return summary(a)


@router.post("/api/answers/{answer_id}/approve")
def approve_answer(answer_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerSummary:
    """409 for a conflict or an unknown answer (answer the question first), and for a gap check's outcome."""
    a = _own(session, ws, answer_id, lock=True)
    _not_gap(session, a)
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

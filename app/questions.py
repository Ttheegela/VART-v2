"""Questions for you (spec 6.9) over the engine's pure planner and its statement re-check."""

import uuid
from collections.abc import Mapping
from datetime import date
from time import monotonic
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import Conflict, NotFound
from app.contracts import ItemInput, ItemLabel, OpenItem, jsonable
from app.db.models import Answer, DocumentLine, InterviewQuestion, Item, Run, SuggestedFill
from app.draft import template_answer
from app.ingest.store import store_statement
from app.interview import OPEN, follow_up, plan_queue, recheck
from app.llm.client import LLMClient
from app.redact import redact_text
from app.runs import CostMeter, _add_cost
from app.services import audit_log
from app.services.llm_budget import spender

MAX_RECHECKS = 8  # per accepted answer (triage row 18): a questionnaire without sections has one topic, None
CONFIDENCE = {"verified": 0.9, "partial": 0.6}
ASKABLE = ("open", "follow_up")
RECHECK_SECONDS = 120.0  # the whole re-check stays well under the 300 s function limit (adversary-3 I2)

__all__ = ["MAX_RECHECKS", "Conflict", "NotFound"]


def statement_filename(position: int) -> str:
    """A server value, never the visitor's item code (triage row 38: the name is printed in every prompt)."""
    return f"answer-{position:03d}.txt"


def _question(
    session: Session, workspace_id: uuid.UUID, question_id: uuid.UUID, *, lock: bool = False
) -> InterviewQuestion:
    """lock: for a write, so two answers to one question take turns (adversary-1 M4)."""
    query = select(InterviewQuestion).where(
        InterviewQuestion.id == question_id, InterviewQuestion.workspace_id == workspace_id
    )
    q = session.scalar(query.with_for_update() if lock else query)
    if q is None:
        raise NotFound()
    return q


def _answer_of(session: Session, run_id: uuid.UUID, item_id: uuid.UUID, *, lock: bool = False) -> Answer:
    query = select(Answer).where(Answer.run_id == run_id, Answer.item_id == item_id)
    return session.scalars(query.with_for_update() if lock else query).one()


def _still_open(a: Answer) -> bool:
    """Open for the interview: not edited or approved by the visitor (adversary-3 M3)."""
    return a.label in OPEN and not a.edited and a.approved_at is None


def _open_pairs(session: Session, run_id: uuid.UUID) -> list[tuple[Item, Answer]]:
    return list(
        session.execute(
            select(Item, Answer)
            .join(Answer, Answer.item_id == Item.id)
            .where(Answer.run_id == run_id, Answer.label.in_(OPEN))
            .order_by(Item.position)
        ).tuples()
    )


def ensure_questions(session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> list[InterviewQuestion]:
    run = session.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id))
    if run is None:
        raise NotFound()
    existing = list(session.scalars(select(InterviewQuestion).where(InterviewQuestion.run_id == run_id)))
    if run.status == "done" and not existing:
        opens = [
            # a conflict's drafted text is the question to ask; the rest are asked as written (P18)
            OpenItem(
                ItemInput(str(i.id), i.question, i.topic),
                cast(ItemLabel, a.label),
                0,
                a.text if a.label == "conflict" else "",
            )
            for i, a in _open_pairs(session, run_id)
        ]
        rows = [
            {
                "workspace_id": workspace_id,
                "run_id": run_id,
                "item_ids": sorted([uuid.UUID(e.key)]),  # the unique key is order-sensitive (Task 1 review)
                "reason": e.reason,
                "rank": n,
                "text": e.question,
            }
            for n, e in enumerate(plan_queue(opens))
        ]
        if rows:
            session.execute(insert(InterviewQuestion).values(rows).on_conflict_do_nothing())
        session.commit()
        existing = list(session.scalars(select(InterviewQuestion).where(InterviewQuestion.run_id == run_id)))
    live = [q for q in existing if q.status in ASKABLE]
    if live:  # a question whose item was meanwhile approved, edited or marked N/A is moot (adversary-3 M4)
        gone = {
            a.item_id
            for a in session.scalars(select(Answer).where(Answer.run_id == run_id))
            if not _still_open(a)
        }
        moot = [q for q in live if q.item_ids[0] in gone]
        for q in moot:
            q.status = "skipped"
        if moot:
            session.commit()
    order = {"open": 0, "follow_up": 0, "answered": 1, "skipped": 1}
    return sorted(existing, key=lambda q: (order[q.status], q.rank))


def answer_question(
    session: Session,
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    text: str,
    llm: LLMClient | None,
    models: Mapping[str, str],
    today: date,
    network: str | None = None,
) -> tuple[InterviewQuestion, Answer | None, list[SuggestedFill]]:
    # Lock order everywhere: answer, question, suggestions (so accept and answer cannot deadlock).
    q = _question(session, workspace_id, question_id)
    item = session.get_one(Item, q.item_ids[0])
    answer = _answer_of(session, q.run_id, item.id, lock=True)
    session.refresh(q, with_for_update=True)
    if q.status not in ASKABLE:
        raise Conflict("This question is already closed.")
    if not _still_open(answer):
        raise Conflict("This item was answered, edited or approved since; the question no longer applies.")
    if q.status == "open" and follow_up(item.question, text) is not None:
        q.status, q.asked_count, q.answer_text = "follow_up", 1, redact_text(text)
        audit_log.record(session, workspace_id, "question.follow_up", ref=str(q.id))
        session.commit()
        return q, None, []
    first = q.answer_text if q.status == "follow_up" else None  # already redacted
    combined = f"{first}\n{text}" if first else text
    run_id, topic, item_id = q.run_id, item.topic, item.id
    try:
        # one transaction: the statement, the answer and the question close together or not at all
        statement = store_statement(
            session,
            workspace_id,
            combined,
            filename=statement_filename(item.position),
            today=today,
            commit=False,
        )
        statement_id = statement.id
        lines = list(
            session.scalars(
                select(DocumentLine.text)
                .where(DocumentLine.document_id == statement_id)
                .order_by(DocumentLine.n)
            )
        )
        answer.label, answer.value, answer.statement_id = "user_confirmed", None, statement_id
        answer.text, answer.confidence, answer.approved_at = " ".join(lines), 1.0, None
        answer.edited = False
        # the engine's evidence no longer describes this answer (pre-flight P7)
        answer.citations, answer.dropped, answer.conflict, answer.scope_note = [], [], None, None
        answer.stances, answer.chunk_ids, answer.retrieval_dropped = [], [], []
        q.status, q.asked_count, q.statement_id = "answered", q.asked_count + 1, statement_id
        q.answer_text = "\n".join(lines)
        session.execute(
            update(SuggestedFill)
            .where(
                SuggestedFill.run_id == run_id,
                SuggestedFill.item_id == item_id,
                SuggestedFill.status == "open",
            )
            .values(status="dismissed")
        )
        audit_log.record(session, workspace_id, "question.answer", ref=str(q.id))
        session.commit()
    except BaseException:
        session.rollback()  # nothing of the answer persists: a retry starts clean
        raise
    found = _suggest(session, workspace_id, run_id, statement_id, topic, item_id, llm, models, network)
    return q, answer, found


def _suggest(
    session: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    statement_id: uuid.UUID,
    topic: str | None,
    answered_item: uuid.UUID,
    llm: LLMClient | None,
    models: Mapping[str, str],
    network: str | None,
) -> list[SuggestedFill]:
    if llm is None:
        return []
    pairs = [(i, a) for i, a in _open_pairs(session, run_id) if i.id != answered_item and i.topic == topic]
    opens = [
        OpenItem(ItemInput(str(i.id), i.question, i.topic), cast(ItemLabel, a.label))
        for i, a in pairs[:MAX_RECHECKS]
    ]
    if not opens:
        return []
    meter = CostMeter(llm)  # recheck's calls are billed like the runner's (adversary-3 I2)
    spend = spender(session, workspace_id, network=network)
    until = monotonic() + RECHECK_SECONDS

    def spend_in_time(step: str) -> bool:
        return monotonic() <= until and spend(step)  # False stops the loop; the rest stay open

    try:
        found = recheck(
            session, workspace_id, statement_id, topic, opens, meter, models["recheck"], spend_in_time
        )
    except Exception:
        session.rollback()  # triage row 37: never leave a refused recheck's row lock to the request's end
        _add_cost(session, run_id, meter.take())
        session.commit()
        raise
    _add_cost(session, run_id, meter.take())
    if found:
        session.execute(
            insert(SuggestedFill)
            .values(
                [
                    {
                        "workspace_id": workspace_id,
                        "run_id": run_id,
                        "item_id": uuid.UUID(sg.key),
                        "statement_id": statement_id,
                        "label": sg.decision.label,
                        "value": sg.decision.value,
                        "text": template_answer(sg.decision),
                        "citations": jsonable(sg.decision.citations),
                        "dropped": jsonable(sg.decision.dropped),
                        "confidence": CONFIDENCE[sg.decision.label],
                    }
                    for sg in found
                ]
            )
            .on_conflict_do_nothing()
        )
    session.commit()
    return list(
        session.scalars(
            select(SuggestedFill).where(
                SuggestedFill.statement_id == statement_id, SuggestedFill.status == "open"
            )
        )
    )


def skip(session: Session, workspace_id: uuid.UUID, question_id: uuid.UUID) -> InterviewQuestion:
    q = _question(session, workspace_id, question_id, lock=True)
    if q.status in ASKABLE:
        q.status = "skipped"
        audit_log.record(session, workspace_id, "question.skip", ref=str(q.id))
    session.commit()
    return q


def accept_suggestion(session: Session, workspace_id: uuid.UUID, suggestion_id: uuid.UUID) -> Answer:
    sg = session.scalar(
        select(SuggestedFill).where(
            SuggestedFill.id == suggestion_id, SuggestedFill.workspace_id == workspace_id
        )
    )
    if sg is None:
        raise NotFound()
    # lock order as answer_question: answer, question, suggestions
    a = _answer_of(session, sg.run_id, sg.item_id, lock=True)
    session.execute(
        update(InterviewQuestion)
        .where(
            InterviewQuestion.run_id == sg.run_id,
            InterviewQuestion.item_ids.contains([sg.item_id]),
            InterviewQuestion.status.in_(ASKABLE),
        )
        .values(status="answered")
    )
    session.refresh(sg, with_for_update=True)
    if sg.status != "open":
        session.rollback()
        raise Conflict("This suggestion was already used or dismissed.")
    if not _still_open(a):
        session.rollback()
        raise Conflict("This item was answered, edited or approved since; the suggestion no longer applies.")
    a.label, a.value, a.text, a.citations = sg.label, sg.value, sg.text, sg.citations
    a.dropped, a.conflict, a.scope_note, a.confidence = sg.dropped, None, None, sg.confidence
    a.stances, a.chunk_ids, a.retrieval_dropped = [], [], []  # the run's stances describe the old answer (P7)
    a.statement_id, a.approved_at, a.edited = sg.statement_id, None, False
    sg.status = "accepted"
    session.execute(
        update(SuggestedFill)
        .where(
            SuggestedFill.run_id == sg.run_id,
            SuggestedFill.item_id == sg.item_id,
            SuggestedFill.status == "open",
        )
        .values(status="dismissed")
    )
    audit_log.record(session, workspace_id, "suggestion.accept", ref=str(sg.id))
    session.commit()
    return a

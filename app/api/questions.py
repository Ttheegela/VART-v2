"""Questions for you (spec 5 step 6, 6.9). Owner: lane 3A-runs (Task 9)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import questions as qs
from app.api.deps import LLMDep, SessionDep, WorkspaceDep
from app.api.errors import limit, network
from app.api.runs import summary
from app.api.schemas import (
    ERRORS,
    SENTENCE_422,
    AnswerQuestionIn,
    AnswerQuestionOut,
    AnswerSummary,
    QuestionOut,
    SuggestionOut,
)
from app.db.models import InterviewQuestion, Item, SuggestedFill
from app.interview import follow_up, high_weight
from app.settings import get_settings

router = APIRouter(tags=["interview"], responses=ERRORS)


def _suggestion_out(session: SessionDep, s: SuggestedFill) -> SuggestionOut:
    item = session.get_one(Item, s.item_id)
    return SuggestionOut(
        id=s.id,
        item_id=s.item_id,
        code=item.code,
        question=item.question,
        label=s.label,
        value=s.value,
        text=s.text,
        status=s.status,
    )


def _out(session: SessionDep, q: InterviewQuestion) -> QuestionOut:
    items = {i.id: i for i in session.scalars(select(Item).where(Item.id.in_(q.item_ids)))}
    ordered = [items[i] for i in q.item_ids]
    item = ordered[0]
    open_fills = (
        []
        if q.statement_id is None
        else list(
            session.scalars(
                select(SuggestedFill).where(
                    SuggestedFill.statement_id == q.statement_id, SuggestedFill.status == "open"
                )
            )
        )
    )
    return QuestionOut(
        id=q.id,
        run_id=q.run_id,
        item_ids=q.item_ids,
        codes=[i.code for i in ordered],
        reason=q.reason,
        text=q.text,
        follow_up=follow_up(item.question, q.answer_text or "") if q.status == "follow_up" else None,
        status=q.status,
        asked_count=q.asked_count,
        high_weight=high_weight(item.topic),
        suggestions=[_suggestion_out(session, s) for s in open_fills],
    )


@router.get("/api/runs/{run_id}/questions")
def list_questions(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> list[QuestionOut]:
    """Open and follow-up questions first, in the planner's order (conflicts, then high-weight topics, then
    the rest), then answered and skipped ones. Empty until the run is done."""
    return [_out(session, q) for q in qs.ensure_questions(session, ws.id, run_id)]


@router.post("/api/questions/{question_id}/answer", responses=SENTENCE_422)
def answer_question(
    question_id: uuid.UUID,
    body: AnswerQuestionIn,
    ws: WorkspaceDep,
    session: SessionDep,
    request: Request,
    llm: LLMDep,
) -> AnswerQuestionOut:
    """Accept the answer, or ask the one follow-up. An accepted answer is stored as a dated, redacted
    statement, the item becomes "Confirmed by you", and open items in the same topic are re-checked (at most
    8, budgeted) for suggested fills; when the model budget or the network's `llm` calls are used up the
    answer is kept and no fills come back. 409 when the question is closed or its item was answered since;
    429 when the network's `interview` cap (60 an hour) is used up."""
    ws_id = ws.id
    limit(request, session, "interview")
    q, answer, found = qs.answer_question(
        session,
        ws_id,
        question_id,
        body.text,
        llm,
        get_settings().models(),
        datetime.now(UTC).date(),
        network(request),
    )
    return AnswerQuestionOut(
        question=_out(session, q),
        answer=summary(answer) if answer else None,
        suggestions=[_suggestion_out(session, s) for s in found],
    )


@router.post("/api/questions/{question_id}/skip")
def skip_question(question_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> QuestionOut:
    return _out(session, qs.skip(session, ws.id, question_id))


@router.post("/api/suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerSummary:
    """Apply a suggested fill to its item's answer (unapproved). 409 when it is not open."""
    return summary(qs.accept_suggestion(session, ws.id, suggestion_id))

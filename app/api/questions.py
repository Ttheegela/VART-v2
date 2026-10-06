"""Questions for you (spec 5 step 6, 6.9). Owner: lane 3A-runs (Task 9)."""

import uuid

from fastapi import APIRouter, Request

from app.api.deps import LLMDep, SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import (
    ERRORS,
    SENTENCE_422,
    AnswerQuestionIn,
    AnswerQuestionOut,
    AnswerSummary,
    QuestionOut,
)

router = APIRouter(tags=["interview"], responses=ERRORS)


@router.get("/api/runs/{run_id}/questions")
def list_questions(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> list[QuestionOut]:
    """Open and follow-up questions first, in the planner's order (conflicts, then high-weight topics, then
    the rest), then answered and skipped ones. Empty until the run is done."""
    raise not_built()


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
    8, budgeted) for suggested fills. 409 when the question is closed; 429 per network (`llm`, per model call)
    or model budget."""
    raise not_built()


@router.post("/api/questions/{question_id}/skip")
def skip_question(question_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> QuestionOut:
    raise not_built()


@router.post("/api/suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerSummary:
    """Apply a suggested fill to its item's answer (unapproved). 409 when it is not open."""
    raise not_built()

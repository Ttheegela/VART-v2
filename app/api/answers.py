"""Answers (spec 5 steps 5 and 7). Owner: lane 3A-runs (Task 8)."""

import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import ERRORS, AnswerDetail, AnswerEdit, AnswerSummary, NotApplicableIn

router = APIRouter(tags=["answers"], responses=ERRORS)


@router.get("/api/answers/{answer_id}")
def get_answer(answer_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerDetail:
    """The Evidence drawer: citations re-read from the stored lines with context, dropped evidence, both
    sides of a conflict, the scope note, the visitor's statement."""
    raise not_built()


@router.patch("/api/answers/{answer_id}")
def edit_answer(
    answer_id: uuid.UUID, edit: AnswerEdit, ws: WorkspaceDep, session: SessionDep
) -> AnswerSummary:
    """Edit the text; the answer becomes unapproved and `edited`."""
    raise not_built()


@router.post("/api/answers/{answer_id}/approve")
def approve_answer(answer_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> AnswerSummary:
    """409 for a conflict or an unknown answer (answer the question first)."""
    raise not_built()


@router.post("/api/answers/{answer_id}/not-applicable")
def mark_not_applicable(
    answer_id: uuid.UUID, body: NotApplicableIn, ws: WorkspaceDep, session: SessionDep
) -> AnswerSummary:
    """Label `na` with the reason in the audit log (spec 6.9)."""
    raise not_built()

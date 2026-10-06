"""Runs and the step runner (spec 6.3). Owner: lane 3A-runs (Task 8)."""

import uuid

from fastapi import APIRouter, Request

from app.api.deps import LLMDep, SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import ERRORS, ApprovedCount, RunOut, RunRowsOut, StepOut

router = APIRouter(tags=["runs"], responses=ERRORS)


@router.post("/api/questionnaires/{questionnaire_id}/runs", status_code=201)
def create_run(
    questionnaire_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep, request: Request
) -> RunOut:
    """A new run over every item, all pending. 422 when the questionnaire has no items yet; 429 per network
    (`run`, 20 an hour); 503 when the demo is full."""
    raise not_built()


@router.post("/api/runs/{run_id}/step")
def step_run(
    run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep, request: Request, llm: LLMDep
) -> StepOut:
    """Claim up to 4 pending items, answer them, write one answer each. Call again while status is
    `running`. 429 with Retry-After when the network (`llm`, 400 steps an hour) or the model budget is used
    up; 503 when model calls are off."""
    raise not_built()


@router.get("/api/runs/{run_id}")
def get_run(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> RunOut:
    raise not_built()


@router.get("/api/runs/{run_id}/answers")
def run_answers(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> RunRowsOut:
    """Every item with its answer (None while pending), in questionnaire order."""
    raise not_built()


@router.post("/api/runs/{run_id}/approve-verified")
def approve_verified(run_id: uuid.UUID, ws: WorkspaceDep, session: SessionDep) -> ApprovedCount:
    """Approve every verified answer not yet approved (design key A)."""
    raise not_built()

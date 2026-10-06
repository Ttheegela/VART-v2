"""The CSF 2.0 gap check over HTTP (CSF spec 5.1, 7). Owner: lane 6B-api (Task 3); stubs until then."""

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import ERRORS, GapOut, GapScope, RunOut

router = APIRouter(tags=["gap"], responses=ERRORS)


@router.get("/api/gap/{scope}")
def gap_view(scope: GapScope, ws: WorkspaceDep, session: SessionDep) -> GapOut:
    """Every outcome of the scope's functions in NIST's order (the core: all 106), each with its tier and,
    once the latest run of the scope's current questionnaire has answered it, its gap label and explanation.
    Labels are decided by code; a not-checked outcome never carries one. Writes nothing; no model call."""
    raise HTTPException(501, "Not built yet.")


@router.post("/api/gap/{scope}/run")
def start_gap(scope: GapScope, ws: WorkspaceDep, session: SessionDep, request: Request) -> RunOut:
    """Start or continue the gap check for this scope, then call POST /api/runs/{id}/step while `running`.
    Creates (or reuses) the workspace's built-in questionnaire for the scope; it is never counted, listed or
    deleted with the visitor's questionnaires. Answers a new run when none exists on it, the running one, or
    the done one with every outcome whose evidence changed since (a new upload) re-opened, all of its parts;
    with nothing changed it stays done and no model is called. 429 per network (`run`, 20 an hour); 503 when
    the demo is full."""
    raise HTTPException(501, "Not built yet.")

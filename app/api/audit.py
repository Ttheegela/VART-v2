"""The visitor's audit log (spec 5 step 7). Owner: lane 3A-runs (Task 8)."""

from fastapi import APIRouter

from app.api.deps import SessionDep, WorkspaceDep
from app.api.errors import not_built
from app.api.schemas import ERRORS, AuditEventOut

router = APIRouter(tags=["audit"], responses=ERRORS)


@router.get("/api/audit")
def list_audit(ws: WorkspaceDep, session: SessionDep) -> list[AuditEventOut]:
    """This workspace's events, newest first, at most 500. Details never hold document text."""
    raise not_built()

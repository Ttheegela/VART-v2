"""The visitor's audit log (spec 5 step 7). Owner: lane 3A-runs (Task 8)."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import ERRORS, AuditEventOut
from app.db.models import AuditEvent

router = APIRouter(tags=["audit"], responses=ERRORS)


@router.get("/api/audit")
def list_audit(ws: WorkspaceDep, session: SessionDep) -> list[AuditEventOut]:
    """This workspace's events, newest first, at most 500. Details never hold document text."""
    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.workspace_id == ws.id).order_by(AuditEvent.id.desc()).limit(500)
    )
    return [AuditEventOut.model_validate(e) for e in rows]

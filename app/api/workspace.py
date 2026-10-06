from datetime import datetime

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete

from app.api.deps import COOKIE_NAME, NewWorkspaceDep, SessionDep, live_workspace
from app.db.models import Workspace
from app.services.workspaces import WORKSPACE_TTL

router = APIRouter()


class WorkspaceOut(BaseModel):
    created_at: datetime
    expires_at: datetime  # the top bar's "expires 23h41m" (design.md)


@router.get("/api/workspace")
def read_workspace(ws: NewWorkspaceDep) -> WorkspaceOut:
    return WorkspaceOut(created_at=ws.created_at, expires_at=ws.created_at + WORKSPACE_TTL)


@router.post("/api/workspace/reset", status_code=204)
def reset_workspace(request: Request, session: SessionDep, response: Response) -> None:
    # Not WorkspaceDep: without a live workspace there is nothing to wipe, and that is a quiet 204, not a 404.
    ws = live_workspace(request, session)
    if ws is not None:
        session.execute(delete(Workspace).where(Workspace.id == ws.id))
        session.commit()
        # Only here: a request without a live workspace (a cross-site POST carries no cookie under Lax) must
        # not log the visitor out (adversary-1 C1).
        response.delete_cookie(COOKIE_NAME)

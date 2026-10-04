from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import delete

from app.api.deps import COOKIE_NAME, SessionDep, WorkspaceDep
from app.db.models import Workspace

router = APIRouter()


class WorkspaceOut(BaseModel):
    created_at: datetime


@router.get("/api/workspace")
def read_workspace(ws: WorkspaceDep) -> WorkspaceOut:
    return WorkspaceOut(created_at=ws.created_at)


@router.post("/api/workspace/reset", status_code=204)
def reset_workspace(ws: WorkspaceDep, session: SessionDep, response: Response) -> None:
    session.execute(delete(Workspace).where(Workspace.id == ws.id))
    session.commit()
    response.delete_cookie(COOKIE_NAME)

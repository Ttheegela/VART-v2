import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from app.api.errors import GONE
from app.db.models import Workspace
from app.db.session import get_session
from app.llm.client import LLMClient, default_client
from app.llm.recorder import RecordingClient, ReplayClient
from app.services.capacity import ensure_capacity
from app.services.ip_limits import client_ip, hit, ip_hash, retry_after
from app.services.workspaces import WORKSPACE_TTL
from app.settings import get_settings

COOKIE_NAME = "vart_ws"
COOKIE_MAX_AGE = int(WORKSPACE_TTL.total_seconds())  # the cookie lives exactly as long as the workspace

SessionDep = Annotated[Session, Depends(get_session)]


def _serializer() -> URLSafeSerializer:
    secret = get_settings().session_secret
    if not secret:
        raise RuntimeError("SESSION_SECRET is not set")
    return URLSafeSerializer(secret, salt="workspace")


def _load(session: Session, raw: str) -> Workspace | None:
    try:
        ws_id = uuid.UUID(str(_serializer().loads(raw)))
    except (BadSignature, ValueError):
        return None
    ws = session.get(Workspace, ws_id)
    # The cleanup job only runs daily; until it does, an expired workspace must not keep working.
    if ws is None or ws.created_at < datetime.now(UTC) - WORKSPACE_TTL:
        return None
    return ws


def live_workspace(request: Request, session: Session) -> Workspace | None:
    """The workspace the request's cookie names while it is still live; never creates one."""
    raw = request.cookies.get(COOKIE_NAME)
    return _load(session, raw) if raw else None


def current_workspace(request: Request, response: Response, session: SessionDep) -> Workspace:
    """The visitor's workspace; a first visit creates one and sets the cookie on `response`.

    Only GET /api/workspace uses this (NewWorkspaceDep). Every other endpoint uses `require_workspace`, so no
    POST mints a workspace or overwrites the visitor's cookie (adversary-1 C1). The frontend calls
    GET /api/workspace (ensureWorkspace) before any workspace-dependent endpoint.
    """
    ws = live_workspace(request, session)
    if ws is not None:
        return ws
    # Hash first (fails before any write when SESSION_SECRET is unset), then the per-network limit, and only
    # then the database-size check, so a flood of refused requests costs one upsert each.
    digest = ip_hash(client_ip(request), get_settings().session_secret)
    allowed = hit(session, digest, "workspace")
    session.commit()  # count the attempt even when it is refused
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="too many new sessions from this network; try again in an hour",
            headers={"Retry-After": str(retry_after("workspace"))},
        )
    ensure_capacity(session)
    ws = Workspace(ip_hash=digest)
    session.add(ws)
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        _serializer().dumps(str(ws.id)),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("VERCEL") == "1",
    )
    return ws


def require_workspace(request: Request, session: SessionDep) -> Workspace:
    """The live workspace the cookie names, or the GONE 404 ("reload the page"); never creates one."""
    ws = live_workspace(request, session)
    if ws is None:
        raise HTTPException(status_code=404, detail=GONE)
    return ws


NewWorkspaceDep = Annotated[Workspace, Depends(current_workspace)]
WorkspaceDep = Annotated[Workspace, Depends(require_workspace)]


def get_llm() -> LLMClient | None:
    settings = get_settings()
    if settings.llm_mode == "live":
        return default_client()
    if os.environ.get("VERCEL") == "1":
        raise RuntimeError("LLM_MODE must be live on Vercel")
    path = Path(settings.llm_recording)
    if settings.llm_mode == "replay":
        return ReplayClient(path)
    live = default_client()
    return RecordingClient(live, path) if live is not None else None


LLMDep = Annotated[LLMClient | None, Depends(get_llm)]

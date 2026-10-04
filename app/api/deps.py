import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.db.session import get_session
from app.llm.client import LLMClient, default_client
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

    FastAPI drops headers set on the injected Response when an endpoint raises (404, 422) or returns a
    Response itself, so such a request never delivers a new cookie. The frontend must therefore call
    GET /api/workspace (ensureWorkspace) before any other endpoint.
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


WorkspaceDep = Annotated[Workspace, Depends(current_workspace)]


def get_llm() -> LLMClient | None:
    return default_client()


LLMDep = Annotated[LLMClient | None, Depends(get_llm)]

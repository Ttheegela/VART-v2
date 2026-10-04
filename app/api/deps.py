import os
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.db.session import get_session
from app.services.capacity import ensure_capacity
from app.services.ip_limits import client_ip, hit, ip_hash
from app.settings import get_settings

COOKIE_NAME = "vart_ws"
COOKIE_MAX_AGE = 24 * 3600

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
    return session.get(Workspace, ws_id)


def current_workspace(request: Request, response: Response, session: SessionDep) -> Workspace:
    raw = request.cookies.get(COOKIE_NAME)
    ws = _load(session, raw) if raw else None
    if ws is not None:
        return ws
    ensure_capacity(session)
    digest = ip_hash(client_ip(request), get_settings().session_secret)
    allowed = hit(session, digest, "workspace")
    session.commit()  # count the attempt even when it is refused
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="too many new sessions from this network; try again in an hour",
            headers={"Retry-After": "3600"},
        )
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

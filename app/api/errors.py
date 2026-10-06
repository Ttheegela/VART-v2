"""Error shapes (docs/CONTRACTS.md, HTTP section): every refusal is {"detail": "<sentence>"}."""

import math
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import ObjectDeletedError
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.contracts import BudgetExhausted
from app.ingest.parse import IngestError
from app.services.ip_limits import client_ip, hit, ip_hash, retry_after
from app.services.llm_budget import Scope as BudgetScope
from app.settings import get_settings

FK_VIOLATION = "23503"
BUDGET: dict[BudgetScope, str] = {
    "workspace": "The model budget for this workspace is used up for this hour; the run can resume then.",
    "network": "Too many model calls from this network this hour; the run can resume then.",
    "hour": "The demo's model budget for this hour is used up; the run can resume then.",
    "day": "The demo's model budget for today is used up; it resets at midnight UTC.",
}
CROSS_SITE = "Cross-site requests are not accepted."
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MODELS_DOWN = "Model calls are failing right now; the run resumes when they return."
GONE = "Your workspace has expired or was reset; reload the page to start a new one."


class NotFound(Exception):
    """An unknown id, or another workspace's id (spec 6.11: both are 404)."""


class Conflict(Exception):
    """The action conflicts with the row's state; the message is the sentence shown."""


class ModelsUnavailable(Exception):
    """The model provider is refusing or not answering (bad key, no credit, rate limit, outage, timeout): the
    run waits instead of writing failed answers. A 503 with Retry-After."""


def network(request: Request) -> str:
    """The caller's network as ip_limits stores it (a salted hash), for `llm_budget.spender(network=)`."""
    return ip_hash(client_ip(request), get_settings().session_secret)


def limit(request: Request, session: Session, kind: str) -> None:
    """Count one `kind` event for the caller's network; past `ip_limits.LIMITS[kind]`, a 429 with Retry-After.
    Every lane uses this one helper (pre-flight P12) for `upload` and `run`. Not for `llm`: that kind is
    counted per model call by `llm_budget.spender(..., network=network(request))` (adversary-1 I2).
    It commits the session (the attempt counts even when refused), so call it first, before any writes."""
    allowed = hit(session, network(request), kind)
    session.commit()
    if not allowed:
        raise HTTPException(
            429,
            "Too many requests from this network; try again later.",
            headers={"Retry-After": str(retry_after(kind))},
        )


def retry_after_budget(now: datetime | None = None, scope: BudgetScope = "workspace") -> int:
    """Seconds until the refusing budget resets: the next hour, or midnight UTC for the daily cap."""
    now = now or datetime.now(UTC)
    nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if scope == "day":
        nxt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(1, math.ceil((nxt - now).total_seconds()))


def _cross_site(headers: Headers) -> bool:
    if headers.get("sec-fetch-site") == "cross-site":
        return True
    origin = headers.get("origin")
    return origin is not None and urlsplit(origin).netloc != headers.get("host")


class SameOriginWrites:
    """Pure ASGI: a state-changing request under /api/ from another site is a 403 before any route runs
    (adversary-1 C1: SameSite=Lax still lets a cross-site form POST through, without the cookie). The app's
    own fetches send Sec-Fetch-Site same-origin and a matching Origin, so they pass."""

    def __init__(self, inner: ASGIApp) -> None:
        self.inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in WRITES
            and scope["path"].startswith("/api/")
            and _cross_site(Headers(scope=scope))
        ):
            await JSONResponse({"detail": CROSS_SITE}, status_code=403)(scope, receive, send)
            return
        await self.inner(scope, receive, send)


def install(app: FastAPI) -> None:
    app.add_middleware(SameOriginWrites)

    @app.exception_handler(NotFound)
    def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": "Not found."}, status_code=404)

    @app.exception_handler(Conflict)
    def _conflict(_: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(IngestError)
    def _ingest(_: Request, exc: IngestError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(BudgetExhausted)
    def _budget(_: Request, exc: BudgetExhausted) -> JSONResponse:
        scope: BudgetScope = getattr(exc, "scope", "workspace")  # llm_budget.Refused carries it
        return JSONResponse(
            {"detail": BUDGET[scope]},
            status_code=429,
            headers={"Retry-After": str(retry_after_budget(scope=scope))},
        )

    @app.exception_handler(ModelsUnavailable)
    def _models(_: Request, exc: ModelsUnavailable) -> JSONResponse:
        return JSONResponse({"detail": MODELS_DOWN}, status_code=503, headers={"Retry-After": "60"})

    @app.exception_handler(NoResultFound)
    @app.exception_handler(ObjectDeletedError)
    def _deleted(_: Request, exc: Exception) -> JSONResponse:
        # a reset between an unlocked read and its locked re-read (adversary-3 M7)
        return JSONResponse({"detail": GONE}, status_code=404)

    @app.exception_handler(IntegrityError)
    def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        # Carry-over (ingest adversary-3): a row for a workspace deleted mid-request is a foreign-key error.
        if getattr(exc.orig, "sqlstate", None) == FK_VIOLATION:
            return JSONResponse({"detail": GONE}, status_code=404)
        raise exc

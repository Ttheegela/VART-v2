"""Error shapes (docs/CONTRACTS.md, HTTP section): every refusal is {"detail": "<sentence>"}."""

import math
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts import BudgetExhausted
from app.ingest.parse import IngestError
from app.services.ip_limits import client_ip, hit, ip_hash, retry_after
from app.settings import get_settings

FK_VIOLATION = "23503"
BUDGET = "The model budget for this workspace is used up for this hour; the run can resume then."
GONE = "Your workspace has expired or was reset; reload the page to start a new one."


class NotFound(Exception):
    """An unknown id, or another workspace's id (spec 6.11: both are 404)."""


class Conflict(Exception):
    """The action conflicts with the row's state; the message is the sentence shown."""


def not_built() -> HTTPException:
    return HTTPException(status_code=501, detail="Not built yet.")


def limit(request: Request, session: Session, kind: str) -> None:
    """Count one `kind` event for the caller's network; past `ip_limits.LIMITS[kind]`, a 429 with Retry-After.
    The attempt is committed even when refused. Every lane uses this one helper (pre-flight P12)."""
    allowed = hit(session, ip_hash(client_ip(request), get_settings().session_secret), kind)
    session.commit()
    if not allowed:
        raise HTTPException(
            429,
            "Too many requests from this network; try again later.",
            headers={"Retry-After": str(retry_after(kind))},
        )


def retry_after_budget(now: datetime | None = None) -> int:
    """Seconds until the next hour, when the hourly model budgets reset."""
    now = now or datetime.now(UTC)
    nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return max(1, math.ceil((nxt - now).total_seconds()))


def install(app: FastAPI) -> None:
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
        return JSONResponse(
            {"detail": BUDGET},
            status_code=429,
            headers={"Retry-After": str(retry_after_budget())},
        )

    @app.exception_handler(IntegrityError)
    def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        # Carry-over (ingest adversary-3): a row for a workspace deleted mid-request is a foreign-key error.
        if getattr(exc.orig, "sqlstate", None) == FK_VIOLATION:
            return JSONResponse({"detail": GONE}, status_code=404)
        raise exc

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from app import __version__
from app.api import (
    answers,
    audit,
    documents,
    errors,
    export,
    internal,
    questionnaires,
    questions,
    runs,
    workspace,
)
from app.db.session import get_engine
from app.observability import flush as flush_traces
from app.observability import has_pending
from app.settings import get_settings

log = logging.getLogger(__name__)
CANARY_STALE = timedelta(hours=36)  # daily cron + slack; older means the cron stopped

app = FastAPI(
    title="VART", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
)


class FlushTraces:
    """Pure ASGI: after the response is fully sent, deliver pending traces."""

    def __init__(self, inner: ASGIApp) -> None:
        self.inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await self.inner(scope, receive, send)
        finally:
            if scope["type"] == "http" and has_pending():
                await run_in_threadpool(flush_traces)


app.add_middleware(FlushTraces)
app.include_router(workspace.router)
app.include_router(internal.router)
errors.install(app)
for module in (documents, questionnaires, runs, answers, questions, export, audit):
    app.include_router(module.router)


class CanaryStatus(BaseModel):
    ok: bool
    at: datetime
    credits_usd: float | None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "unavailable"]
    canary: CanaryStatus | None = None


class VersionOut(BaseModel):
    version: str
    models: dict[str, str]


@app.get("/api/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
def health() -> JSONResponse:
    try:
        with get_engine().connect() as conn, conn.begin():
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            row = conn.execute(
                text("SELECT ok, at, detail -> 'credits_usd' FROM canary_runs ORDER BY at DESC LIMIT 1")
            ).first()
    except (SQLAlchemyError, RuntimeError):  # RuntimeError: DATABASE_URL unset
        log.exception("health check: database unavailable")
        return JSONResponse({"status": "degraded", "db": "unavailable"}, status_code=503)
    body: dict[str, object] = {"status": "ok", "db": "ok", "canary": None}
    if row is not None:
        ok, at, credits = row
        body["canary"] = {"ok": bool(ok), "at": at.isoformat(), "credits_usd": credits}
        if not ok or at < datetime.now(UTC) - CANARY_STALE:
            body["status"] = "degraded"
    if os.environ.get("VERCEL") == "1" and get_settings().llm_mode != "live":
        body["status"] = (
            "degraded"  # get_llm refuses every step there: say so at deploy, not on the first run
        )
    return JSONResponse(body)


@app.get("/api/version")
def version() -> VersionOut:
    return VersionOut(version=__version__, models=get_settings().models())


def mount_frontend(target: FastAPI, directory: Path) -> None:
    """Serve the built UI as low-priority routes; skipped when there is no build (tests, API-only dev)."""
    if directory.is_dir():
        target.frontend("/", directory=directory, fallback="index.html")


mount_frontend(app, Path(__file__).resolve().parent.parent / "public")

"""Per-network limits for actions that create rows or spend money. Counts live in Postgres (no Redis)."""

import hashlib
import hmac
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db.models import IpLimit

# (events allowed, window) per kind; generous for people, tight for scripts.
LIMITS: dict[str, tuple[int, timedelta]] = {
    "workspace": (20, timedelta(hours=1)),
    "upload": (60, timedelta(hours=1)),
    "run": (20, timedelta(hours=1)),
}
KEEP = timedelta(days=2)


def client_ip(request: Request) -> str:
    # Vercel sets x-real-ip and overwrites x-forwarded-for, so clients cannot spoof either there.
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_hash(ip: str, secret: str) -> str:
    if not secret:
        # An empty key still hashes, but an unsalted digest of an IPv4 address is trivial to reverse, and the
        # digest is stored. Fail before any caller writes one.
        raise RuntimeError("SESSION_SECRET is not set")
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


def _window_start(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


def retry_after(kind: str, now: datetime | None = None) -> int:
    """Whole seconds until the current window for this kind ends (never less than 1)."""
    now = now or datetime.now(UTC)
    window = LIMITS[kind][1]
    return math.ceil((_window_start(now, window) + window - now).total_seconds())


def bump(session: Session, ip_digest: str, kind: str, window_start: datetime) -> int:
    """Add one to a counter row (created at 1) and return its new value; atomic under concurrency."""
    stmt = (
        insert(IpLimit)
        .values(ip_hash=ip_digest, window_start=window_start, kind=kind, hits=1)
        .on_conflict_do_update(
            index_elements=[IpLimit.ip_hash, IpLimit.window_start, IpLimit.kind],
            set_={"hits": IpLimit.hits + 1},
        )
        .returning(IpLimit.hits)
    )
    return int(session.execute(stmt).scalar_one())


def hit(session: Session, ip_digest: str, kind: str, now: datetime | None = None) -> bool:
    """Count one event; False when this network is over its limit in the current window."""
    limit, window = LIMITS[kind]
    start = _window_start(now or datetime.now(UTC), window)
    return bump(session, ip_digest, kind, start) <= limit


def purge(session: Session, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - KEEP
    result = session.execute(delete(IpLimit).where(IpLimit.window_start < cutoff))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]

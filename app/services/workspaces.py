from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import CanaryRun, Workspace
from app.services.ip_limits import purge

WORKSPACE_TTL = timedelta(hours=24)
CANARY_KEEP = timedelta(days=30)


def cleanup_expired(session: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    workspaces = session.execute(delete(Workspace).where(Workspace.created_at < now - WORKSPACE_TTL))
    limits = purge(session, now)
    canaries = session.execute(delete(CanaryRun).where(CanaryRun.at < now - CANARY_KEEP))
    session.commit()
    return {
        "workspaces": int(workspaces.rowcount or 0),  # type: ignore[attr-defined]
        "ip_limits": limits,
        "canary_runs": int(canaries.rowcount or 0),  # type: ignore[attr-defined]
    }

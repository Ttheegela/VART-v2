"""Hourly model-call budgets per workspace and step, plus one global cap (PriorPath pattern, generalized)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import LlmUsage

# Calls per workspace per hour. A 60-item questionnaire needs about 60 stance + 50 draft calls.
CAPS: dict[str, int] = {"stance": 150, "draft": 120, "classify": 40, "recheck": 60}
GLOBAL_PER_HOUR = 1500  # all workspaces, all steps


def _hour(now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)


def _global_used(session: Session, hour: datetime) -> int:
    # Count each workspace/step at most up to its own cap, so refused retries from one workspace
    # can't use up the global budget for everyone else.
    per_workspace = case(
        *[(LlmUsage.kind == kind, func.least(LlmUsage.calls, cap)) for kind, cap in CAPS.items()],
        else_=LlmUsage.calls,
    )
    total = session.scalar(
        select(func.coalesce(func.sum(per_workspace), 0)).where(LlmUsage.hour_start == hour)
    )
    return int(total or 0)


def remaining(session: Session, workspace_id: uuid.UUID, kind: str, now: datetime | None = None) -> int:
    hour = _hour(now)
    used = session.scalar(
        select(LlmUsage.calls).where(
            LlmUsage.workspace_id == workspace_id, LlmUsage.hour_start == hour, LlmUsage.kind == kind
        )
    )
    own = CAPS[kind] - (used or 0)
    return max(0, min(own, GLOBAL_PER_HOUR - _global_used(session, hour)))


def try_consume(session: Session, workspace_id: uuid.UUID, kind: str, now: datetime | None = None) -> bool:
    cap = CAPS[kind]  # KeyError for an unknown step: a programming error, not a visitor error
    hour = _hour(now)
    stmt = (
        insert(LlmUsage)
        .values(workspace_id=workspace_id, hour_start=hour, kind=kind, calls=1)
        .on_conflict_do_update(
            index_elements=[LlmUsage.workspace_id, LlmUsage.hour_start, LlmUsage.kind],
            set_={"calls": LlmUsage.calls + 1},
        )
        .returning(LlmUsage.calls)
    )
    if int(session.execute(stmt).scalar_one()) > cap:
        return False
    return _global_used(session, hour) <= GLOBAL_PER_HOUR

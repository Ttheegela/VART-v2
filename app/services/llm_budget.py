"""Hourly model-call budgets per workspace and step, plus global hourly and daily caps (PriorPath pattern)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import IpLimit, LlmUsage
from app.services.ip_limits import bump

# Calls per workspace per hour. A 60-item questionnaire needs about 60 stance + 50 draft calls.
CAPS: dict[str, int] = {"stance": 150, "draft": 120, "classify": 40, "recheck": 60}
GLOBAL_PER_HOUR = 1500  # all workspaces, all steps
GLOBAL_PER_DAY = 4000  # the key must outlive days of abuse, not hours (1500 an hour is 36,000 calls a day)
# The global counts are rows in ip_limits that no workspace owns. Summing llm_usage instead would let a
# workspace reset (which deletes its usage rows) refund the budget, so a script could reset past the cap.
GLOBAL_KEY, GLOBAL_KIND, GLOBAL_DAY_KIND = "global-llm", "llm", "llm-day"


def _hour(now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)


def _day(hour: datetime) -> datetime:
    return hour.replace(hour=0)  # midnight UTC of the hour's day


def _global_used(session: Session, kind: str, window_start: datetime) -> int:
    used = session.scalar(
        select(IpLimit.hits).where(
            IpLimit.ip_hash == GLOBAL_KEY, IpLimit.window_start == window_start, IpLimit.kind == kind
        )
    )
    return used or 0


def remaining(session: Session, workspace_id: uuid.UUID, kind: str, now: datetime | None = None) -> int:
    hour = _hour(now)
    used = session.scalar(
        select(LlmUsage.calls).where(
            LlmUsage.workspace_id == workspace_id, LlmUsage.hour_start == hour, LlmUsage.kind == kind
        )
    )
    own = CAPS[kind] - (used or 0)
    hourly = GLOBAL_PER_HOUR - _global_used(session, GLOBAL_KIND, hour)
    daily = GLOBAL_PER_DAY - _global_used(session, GLOBAL_DAY_KIND, _day(hour))
    return max(0, min(own, hourly, daily))


def try_consume(session: Session, workspace_id: uuid.UUID, kind: str, now: datetime | None = None) -> bool:
    """Spend one call of this step; False when the step's hourly cap or a global cap (hour or day) is used up.

    Callers must commit right after: the upserted rows stay locked until then, and the global counter rows are
    shared by every workspace, so never hold this transaction open across a model call.
    """
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
        return False  # refused here, so retries never touch the shared counter
    if bump(session, GLOBAL_KEY, GLOBAL_KIND, hour) > GLOBAL_PER_HOUR:
        return False  # refused here, so calls the hourly cap turns away never spend the day's allowance
    return bump(session, GLOBAL_KEY, GLOBAL_DAY_KIND, _day(hour)) <= GLOBAL_PER_DAY

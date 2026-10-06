"""Hourly model-call budgets per workspace and step, plus global hourly and daily caps (PriorPath pattern)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.contracts import BudgetExhausted
from app.db.models import IpLimit, LlmUsage
from app.services.ip_limits import LIMITS, _window_start, bump, hit

Scope = Literal["workspace", "network", "hour", "day"]  # which cap refused a call (adversary-1 I5)


class Refused(BudgetExhausted):
    """BudgetExhausted naming the cap that refused, so the 429 says which and when it resets
    (app.api.errors). A plain BudgetExhausted reads as the workspace scope."""

    def __init__(self, step: str, scope: Scope) -> None:
        super().__init__(step)
        self.scope: Scope = scope


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


def refusal_scope(
    session: Session,
    workspace_id: uuid.UUID,
    kind: str,
    network: str | None = None,
    now: datetime | None = None,
) -> Scope:
    """Which cap refused the last `kind` call: a refusal leaves its counter over the cap for the window, and
    the caps are checked in the order the spender spends them: network, workspace, global hour, global day."""
    now = now or datetime.now(UTC)
    hour = _hour(now)
    if network is not None:
        limit, window = LIMITS["llm"]
        used = session.scalar(
            select(IpLimit.hits).where(
                IpLimit.ip_hash == network,
                IpLimit.window_start == _window_start(now, window),
                IpLimit.kind == "llm",
            )
        )
        if (used or 0) > limit:
            return "network"
    used = session.scalar(
        select(LlmUsage.calls).where(
            LlmUsage.workspace_id == workspace_id, LlmUsage.hour_start == hour, LlmUsage.kind == kind
        )
    )
    if (used or 0) > CAPS[kind]:
        return "workspace"
    if _global_used(session, GLOBAL_KIND, hour) > GLOBAL_PER_HOUR:
        return "hour"
    return "day"


def spender(session: Session, workspace_id: uuid.UUID, network: str | None = None) -> Callable[[str], bool]:
    """The budget hook engine code calls before every model call (app.contracts.Spend). It spends one call of
    that step and commits at once, so the shared global counter row is never held across a model call and no
    transaction ever holds two try_consume calls (Plan 1A Task 3 review).

    With `network` (the request's `ip_hash`, `app.api.errors.network`), each call also counts one `llm` event
    for that network first: the per-network `llm` limit is per model call, not per request (adversary-1 I2).
    A call the network limit refuses spends no workspace or global budget.

    Commits everything pending in `session`, not only the budget row. Read what you need from ORM objects into
    plain values before calling it; after it, run no query and touch no ORM attribute until the model call
    returns. One spender per session; `step` is a key of `CAPS`."""

    def spend(step: str) -> bool:
        allowed = (network is None or hit(session, network, "llm")) and try_consume(
            session, workspace_id, step
        )
        session.commit()
        return allowed

    return spend

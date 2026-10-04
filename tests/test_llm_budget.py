import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.main import app
from app.services import llm_budget
from app.services.llm_budget import remaining, try_consume
from tests import factories as f

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def test_each_step_has_its_own_hourly_cap(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 2)
    with Session(db) as s:
        ws = f.workspace(s)
        assert [try_consume(s, ws.id, "stance", NOW) for _ in range(3)] == [True, True, False]
        assert try_consume(s, ws.id, "draft", NOW) is True
        assert remaining(s, ws.id, "stance", NOW) == 0


def test_the_global_cap_is_shared(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 5)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 3)
    with Session(db) as s:
        a, b = f.workspace(s), f.workspace(s)
        assert [try_consume(s, a.id, "stance", NOW) for _ in range(2)] == [True, True]
        assert try_consume(s, b.id, "stance", NOW) is True
        assert try_consume(s, b.id, "stance", NOW) is False


def test_refused_retries_do_not_drain_the_global_cap(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 2)
    with Session(db) as s:
        a, b = f.workspace(s), f.workspace(s)
        for _ in range(5):
            try_consume(s, a.id, "stance", NOW)  # 1 allowed, 4 refused
        assert try_consume(s, b.id, "stance", NOW) is True


def test_reset_does_not_refund_the_global_cap(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 5)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 3)
    visitor_a = TestClient(app)
    visitor_a.get("/api/workspace")
    with Session(db) as s:
        a = s.scalars(select(Workspace.id)).one()
        assert [try_consume(s, a, "stance", NOW) for _ in range(3)] == [True, True, True]
        s.commit()
    assert visitor_a.post("/api/workspace/reset").status_code == 204  # A and its llm_usage rows are gone
    with Session(db) as s:
        b = f.workspace(s)
        assert try_consume(s, b.id, "stance", NOW) is False
        assert remaining(s, b.id, "stance", NOW) == 0


def test_the_global_daily_cap_outlasts_the_hourly_one(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 2)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_DAY", 3)
    with Session(db) as s:
        ws = f.workspace(s)
        # The third call is turned away by the hour, so it does not spend the day's allowance ...
        assert [try_consume(s, ws.id, "stance", NOW) for _ in range(3)] == [True, True, False]
        # ... which leaves exactly one call for the next hour: the day's third.
        later = NOW + timedelta(hours=1)
        assert [try_consume(s, ws.id, "stance", later) for _ in range(2)] == [True, False]
        assert try_consume(s, ws.id, "stance", NOW + timedelta(days=1)) is True  # a new day, a new allowance


def test_the_day_starts_at_midnight_utc(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_DAY", 1)
    late = datetime(2026, 10, 3, 23, 0, tzinfo=UTC)
    with Session(db) as s:
        ws = f.workspace(s)
        assert try_consume(s, ws.id, "stance", late) is True
        assert try_consume(s, ws.id, "stance", late + timedelta(minutes=59)) is False  # still 3 October
        assert try_consume(s, ws.id, "stance", late + timedelta(hours=1)) is True  # 00:00 on 4 October


def test_remaining_counts_the_daily_cap_too(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 5)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_DAY", 3)
    with Session(db) as s:
        ws = f.workspace(s)
        assert remaining(s, ws.id, "stance", NOW) == 3  # the day is the tightest of step 10, hour 5, day 3
        assert [try_consume(s, ws.id, "stance", NOW) for _ in range(2)] == [True, True]
        assert remaining(s, ws.id, "stance", NOW) == 1
        later = NOW + timedelta(hours=1)  # a fresh hour with 5 left in it, but only 1 left in the day
        assert remaining(s, ws.id, "stance", later) == 1
        assert try_consume(s, ws.id, "stance", later) is True
        assert remaining(s, ws.id, "stance", later) == 0
        assert remaining(s, ws.id, "stance", NOW + timedelta(days=1)) == 3


def test_unknown_step_is_a_programming_error(db: Engine) -> None:
    with Session(db) as s, pytest.raises(KeyError):
        try_consume(s, uuid.uuid4(), "poetry", NOW)

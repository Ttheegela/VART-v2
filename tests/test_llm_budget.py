import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

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


def test_unknown_step_is_a_programming_error(db: Engine) -> None:
    with Session(db) as s, pytest.raises(KeyError):
        try_consume(s, uuid.uuid4(), "poetry", NOW)

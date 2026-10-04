import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import LlmUsage
from app.services import llm_budget
from app.services.llm_budget import spender
from tests import factories as f


def test_spend_commits_each_call_at_once(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    with Session(db) as s:
        ws_id = f.workspace(s).id
        s.commit()
        spend = spender(s, ws_id)
        assert spend("stance") is True
        assert not s.in_transaction()  # nothing held open across the model call that follows
        assert spend("stance") is False
    with Session(db) as other:
        assert other.scalar(select(LlmUsage.calls).where(LlmUsage.workspace_id == ws_id)) == 2

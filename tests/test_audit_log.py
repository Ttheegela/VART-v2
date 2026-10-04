from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent
from app.services.audit_log import record
from tests import factories as f


def test_record_adds_an_event(db: Engine) -> None:
    with Session(db) as s:
        ws = f.workspace(s)
        record(s, ws.id, "approve", ref="a1", detail={"label": "verified"})
        s.commit()
        event = s.scalars(select(AuditEvent)).one()
        assert (event.actor, event.action, event.ref, event.detail) == (
            "visitor",
            "approve",
            "a1",
            {"label": "verified"},
        )

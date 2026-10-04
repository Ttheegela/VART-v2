import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def record(
    session: Session,
    workspace_id: uuid.UUID,
    action: str,
    *,
    actor: str = "visitor",
    ref: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(workspace_id=workspace_id, actor=actor, action=action, ref=ref, detail=detail or {})
    session.add(event)
    return event

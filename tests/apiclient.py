"""A visitor with a workspace cookie, for API tests."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.main import app


def visitor(db: Engine) -> tuple[TestClient, uuid.UUID]:
    client = TestClient(app)
    assert client.get("/api/workspace").status_code == 200
    with Session(db) as s:
        ws_id = s.scalars(select(Workspace.id).order_by(Workspace.created_at.desc())).first()
    assert ws_id is not None
    return client, ws_id

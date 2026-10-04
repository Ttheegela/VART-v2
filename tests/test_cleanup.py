from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.models import CanaryRun, Workspace
from app.main import app
from app.services.ip_limits import hit
from app.services.workspaces import cleanup_expired


def test_cleanup_removes_expired_rows(db: Engine) -> None:
    now = datetime.now(UTC)
    with Session(db) as s:
        s.add(Workspace(created_at=now - timedelta(hours=25)))
        s.add(Workspace(created_at=now - timedelta(hours=1)))
        s.add(CanaryRun(ok=True, at=now - timedelta(days=31)))
        s.add(CanaryRun(ok=True, at=now - timedelta(days=1)))
        hit(s, "old-ip", "upload", now - timedelta(days=3))
        s.commit()
        assert cleanup_expired(s, now) == {"workspaces": 1, "ip_limits": 1, "canary_runs": 1}
        assert s.scalar(select(func.count()).select_from(Workspace)) == 1


def test_cleanup_endpoint_needs_the_cron_secret(db: Engine) -> None:
    c = TestClient(app)
    assert c.get("/api/internal/cleanup").status_code == 401
    assert c.get("/api/internal/cleanup", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = c.get("/api/internal/cleanup", headers={"Authorization": "Bearer test-cron-secret"})
    assert ok.status_code == 200
    assert set(ok.json()) == {"workspaces", "ip_limits", "canary_runs"}


def test_cleanup_is_closed_when_no_secret_is_configured(db: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CRON_SECRET", "")
    r = TestClient(app).get("/api/internal/cleanup", headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_internal_routes_are_not_in_the_public_schema() -> None:
    assert not [p for p in app.openapi()["paths"] if p.startswith("/api/internal")]

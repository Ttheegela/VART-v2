from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.db.models import IpLimit, Workspace
from app.main import app
from app.services import capacity, ip_limits


@pytest.fixture
def client(db: Engine) -> TestClient:
    return TestClient(app)


def _count(db: Engine) -> int:
    with Session(db) as s:
        return int(s.scalar(select(func.count()).select_from(Workspace)) or 0)


def test_first_visit_creates_a_workspace_and_sets_a_cookie(client: TestClient, db: Engine) -> None:
    r = client.get("/api/workspace")
    assert r.status_code == 200
    assert "created_at" in r.json()
    cookie = r.headers["set-cookie"].lower()
    assert "vart_ws=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert _count(db) == 1


def test_the_cookie_reuses_the_workspace(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    client.get("/api/workspace")
    assert _count(db) == 1


def test_cookie_for_a_deleted_workspace_starts_fresh(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    with db.begin() as conn:
        conn.execute(text("delete from workspaces"))
    r = client.get("/api/workspace")
    assert r.status_code == 200
    assert _count(db) == 1
    assert client.get("/api/workspace").status_code == 200  # the replacement cookie sticks
    assert _count(db) == 1


def test_cookie_for_an_expired_workspace_starts_fresh(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    with db.begin() as conn:  # the daily cleanup has not run yet
        conn.execute(text("update workspaces set created_at = now() - interval '25 hours'"))
    r = client.get("/api/workspace")
    assert r.status_code == 200
    assert "vart_ws=" in r.headers.get("set-cookie", "")  # a new cookie was issued
    assert _count(db) == 2  # the stale row waits for the cleanup job


def test_tampered_cookie_starts_fresh(client: TestClient, db: Engine) -> None:
    client.cookies.set("vart_ws", "not-a-signed-value")
    assert client.get("/api/workspace").status_code == 200
    assert _count(db) == 1


def test_reset_deletes_the_workspace_and_clears_the_cookie(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    r = client.post("/api/workspace/reset")
    assert r.status_code == 204
    assert 'vart_ws=""' in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"].lower()
    assert _count(db) == 0


def test_new_workspaces_per_ip_are_limited(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "workspace", (2, timedelta(hours=1)))
    statuses = []
    for _ in range(3):
        fresh = TestClient(app)  # no cookie: a new visitor each time
        statuses.append(fresh.get("/api/workspace", headers={"x-real-ip": "203.0.113.7"}))
    assert [r.status_code for r in statuses] == [200, 200, 429]
    assert 0 < int(statuses[2].headers["retry-after"]) <= 3600
    other = TestClient(app).get("/api/workspace", headers={"x-real-ip": "198.51.100.1"})
    assert other.status_code == 200
    assert _count(db) == 3


def test_refused_requests_do_not_run_the_capacity_check(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "workspace", (1, timedelta(hours=1)))
    checks: list[int] = []

    def not_full(_session: Session) -> bool:
        checks.append(1)
        return False

    monkeypatch.setattr(capacity, "demo_is_full", not_full)
    headers = {"x-real-ip": "203.0.113.9"}
    assert TestClient(app).get("/api/workspace", headers=headers).status_code == 200
    assert TestClient(app).get("/api/workspace", headers=headers).status_code == 429
    assert len(checks) == 1  # the refused request never reached the size check


def test_a_full_demo_refuses_new_workspaces(
    client: TestClient, db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capacity, "demo_is_full", lambda _session: True)
    r = client.get("/api/workspace")
    assert r.status_code == 503
    assert "demo is full" in r.json()["detail"]
    assert _count(db) == 0


def test_missing_session_secret_fails_before_anything_is_written(
    client: TestClient, db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "")
    with pytest.raises(RuntimeError, match="SESSION_SECRET is not set"):
        client.get("/api/workspace")
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(IpLimit)) == 0
    assert _count(db) == 0


def test_cookie_is_secure_on_vercel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    assert "secure" in client.get("/api/workspace").headers["set-cookie"].lower()

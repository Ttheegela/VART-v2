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


def _new_session_hits(db: Engine) -> int:
    """Everything counted so far against the per-network new-session limit."""
    with Session(db) as s:
        hits = s.scalar(select(func.coalesce(func.sum(IpLimit.hits), 0)).where(IpLimit.kind == "workspace"))
        return int(hits or 0)


@pytest.mark.parametrize("state", ["no cookie", "tampered cookie", "deleted workspace", "expired workspace"])
def test_reset_without_a_live_workspace_creates_nothing_and_charges_nothing(
    client: TestClient, db: Engine, state: str
) -> None:
    if state == "tampered cookie":
        client.cookies.set("vart_ws", "not-a-signed-value")
    elif state != "no cookie":
        client.get("/api/workspace")  # one workspace, one counted new session
        with db.begin() as conn:
            if state == "deleted workspace":
                conn.execute(text("delete from workspaces"))
            else:  # the stale row waits for the cleanup job
                conn.execute(text("update workspaces set created_at = now() - interval '25 hours'"))
    rows, hits = _count(db), _new_session_hits(db)
    r = client.post("/api/workspace/reset")
    assert r.status_code == 204
    cookies = r.headers.get_list("set-cookie")  # only the clearing one, no fresh cookie before it
    assert len(cookies) == 1
    assert 'vart_ws=""' in cookies[0] or "max-age=0" in cookies[0].lower()
    assert (_count(db), _new_session_hits(db)) == (rows, hits)


def test_twenty_load_and_reset_cycles_do_not_lock_the_network_out(client: TestClient, db: Engine) -> None:
    headers = {"x-real-ip": "203.0.113.7"}
    limit = ip_limits.LIMITS["workspace"][0]
    for cycle in range(limit):
        assert client.get("/api/workspace", headers=headers).status_code == 200, cycle
        # a double click or a retry: the second reset has no cookie left to go on
        resets = [client.post("/api/workspace/reset", headers=headers).status_code for _ in range(2)]
        assert resets == [204, 204], cycle
    assert _new_session_hits(db) == limit  # one per load, none per reset
    # The limit is on new sessions and every load after a reset is one, so the next load is refused ...
    assert client.get("/api/workspace", headers=headers).status_code == 429
    # ... but a wipe never is.
    assert client.post("/api/workspace/reset", headers=headers).status_code == 204


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

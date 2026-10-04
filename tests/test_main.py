from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

import app.main as main
from app.db.models import CanaryRun
from app.main import app, mount_frontend


@pytest.fixture
def client(db: Engine) -> TestClient:
    return TestClient(app)


def _canary(db: Engine, ok: bool, age: timedelta, credits: float | None = 7.5) -> None:
    with Session(db) as s:
        s.add(CanaryRun(ok=ok, at=datetime.now(UTC) - age, detail={"credits_usd": credits}))
        s.commit()


def test_healthy_with_no_canary_yet(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert '"status":"ok"' in r.text  # the exact bytes UptimeRobot's keyword monitor looks for
    assert r.json() == {"status": "ok", "db": "ok", "canary": None}


def test_healthy_with_a_fresh_passing_canary(client: TestClient, db: Engine) -> None:
    _canary(db, ok=True, age=timedelta(hours=2))
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["canary"]["ok"] is True and body["canary"]["credits_usd"] == 7.5


def test_degraded_when_the_last_canary_failed(client: TestClient, db: Engine) -> None:
    _canary(db, ok=True, age=timedelta(hours=30))
    _canary(db, ok=False, age=timedelta(hours=1))
    r = client.get("/api/health")
    assert r.status_code == 200 and '"status":"degraded"' in r.text


def test_degraded_when_the_canary_is_stale(client: TestClient, db: Engine) -> None:
    _canary(db, ok=True, age=timedelta(hours=40))
    assert client.get("/api/health").json()["status"] == "degraded"


def test_a_passing_canary_inside_the_window_stays_healthy(client: TestClient, db: Engine) -> None:
    # with the 40 h case above, this pins the 36 h limit from both sides
    _canary(db, ok=True, age=timedelta(hours=30))
    r = client.get("/api/health")
    assert r.status_code == 200 and '"status":"ok"' in r.text


def test_503_when_the_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = create_engine(
        "postgresql+psycopg://x:y@127.0.0.1:1/nothing_test", connect_args={"connect_timeout": 1}
    )
    monkeypatch.setattr(main, "get_engine", lambda: dead)
    r = TestClient(app).get("/api/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "db": "unavailable"}
    assert "x:y" not in r.text


def test_503_when_the_database_url_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # The uncached factory with DATABASE_URL removed raises the real RuntimeError from database_url().
    monkeypatch.setattr(main, "get_engine", main.get_engine.__wrapped__)
    monkeypatch.delenv("DATABASE_URL")
    r = TestClient(app).get("/api/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "db": "unavailable"}
    assert "DATABASE_URL" not in r.text


def test_version_lists_the_models(client: TestClient) -> None:
    body = client.get("/api/version").json()
    assert body["version"] == "2.0.0.dev0"
    assert set(body["models"]) == {"stance", "draft", "classify", "judge"}


def test_ui_is_served_when_built(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    target = FastAPI()
    mount_frontend(target, tmp_path)
    assert TestClient(target).get("/").text == "<div id=root></div>"


def test_no_ui_mount_without_a_build(tmp_path: Path) -> None:
    target = FastAPI()
    mount_frontend(target, tmp_path / "missing")
    assert TestClient(target).get("/").status_code == 404


def test_pending_traces_are_flushed_after_the_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    flushed = []
    monkeypatch.setattr(main, "has_pending", lambda: True)
    monkeypatch.setattr(main, "flush_traces", lambda: flushed.append(1))
    client.get("/api/version")
    assert flushed == [1]

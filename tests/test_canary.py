import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api.deps import get_llm
from app.db.models import CanaryRun
from app.llm.client import LLMError
from app.main import app
from app.services import canary
from app.services.canary import remaining_credits, run_canary
from app.settings import get_settings
from tests.fakes import FakeLLM

OK = '{"ok": true}'


@pytest.fixture(autouse=True)
def four_models(monkeypatch: pytest.MonkeyPatch) -> None:
    for step, model in (("STANCE", "m/a"), ("DRAFT", "m/b"), ("CLASSIFY", "m/c"), ("JUDGE", "m/d")):
        monkeypatch.setenv(f"{step}_MODEL", model)


def _http(payload: object, status: int = 200) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=payload)))


def test_every_model_answers_and_credits_are_fine(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, FakeLLM([OK] * 4), _http({"data": {"limit_remaining": 5.0}}), get_settings())
    assert row.ok is True
    assert row.detail == {"models": {"m/a": "ok", "m/b": "ok", "m/c": "ok", "m/d": "ok"}, "credits_usd": 5.0}


def test_a_failing_model_fails_the_canary(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(
            s, FakeLLM([OK, LLMError("draft: NotFoundError"), OK, OK]), _http({}), get_settings()
        )
    assert row.ok is False
    assert row.detail["models"]["m/b"].startswith("draft: NotFoundError")


def test_low_credits_fail_the_canary(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, FakeLLM([OK] * 4), _http({"data": {"limit_remaining": 0.4}}), get_settings())
    assert row.ok is False and row.detail["credits_usd"] == 0.4


def test_no_key_fails_the_canary(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, None, _http({}), get_settings())
    assert row.ok is False and "OPENROUTER_API_KEY" in row.detail["error"]


@pytest.mark.parametrize(
    ("payload", "status", "expected"),
    [
        ({"data": {"limit_remaining": 3.5}}, 200, 3.5),
        ({"data": {"limit_remaining": None}}, 200, None),
        ({"error": "nope"}, 500, None),
        ("not an object", 200, None),
    ],
)
def test_remaining_credits(payload: object, status: int, expected: float | None) -> None:
    assert remaining_credits(_http(payload, status), "k") == expected


def test_remaining_credits_survives_network_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert remaining_credits(httpx.Client(transport=httpx.MockTransport(boom)), "k") is None


@pytest.mark.parametrize("data", [None, "x", [1]])
def test_remaining_credits_ignores_a_data_field_that_is_not_an_object(data: object) -> None:
    assert remaining_credits(_http({"data": data}), "k") is None


def test_canary_endpoint_needs_the_cron_secret_and_feeds_health(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(canary, "remaining_credits", lambda http, key: 9.0)
    app.dependency_overrides[get_llm] = lambda: FakeLLM([OK] * 4)
    try:
        c = TestClient(app)
        assert c.get("/api/internal/canary").status_code == 401
        r = c.get("/api/internal/canary", headers={"Authorization": "Bearer test-cron-secret"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert c.get("/api/health").json()["canary"]["credits_usd"] == 9.0
    finally:
        app.dependency_overrides.clear()
    with Session(db) as s:
        assert len(s.scalars(select(CanaryRun)).all()) == 1

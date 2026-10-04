import pytest

from app.settings import DEFAULT_MODELS, get_settings


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "s3")
    monkeypatch.setenv("STANCE_MODEL", "acme/fast")
    monkeypatch.setenv("CANARY_MIN_CREDITS_USD", "5")
    s = get_settings()
    assert s.session_secret == "s3"
    assert s.models()["stance"] == "acme/fast"
    assert s.canary_min_credits_usd == 5.0


def test_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("STANCE_MODEL", "DRAFT_MODEL", "CLASSIFY_MODEL", "JUDGE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert get_settings().models() == DEFAULT_MODELS


def test_secrets_have_no_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SESSION_SECRET", "CRON_SECRET", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    s = get_settings()
    assert (s.session_secret, s.cron_secret, s.openrouter_api_key) == ("", "", "")


def test_blank_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANCE_MODEL", "")
    monkeypatch.setenv("SESSION_SECRET", "")
    s = get_settings()
    assert s.models()["stance"] == DEFAULT_MODELS["stance"]
    assert s.session_secret == ""

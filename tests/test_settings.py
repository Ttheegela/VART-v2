import json
from pathlib import Path

import pytest

from app.settings import DEFAULT_MODELS, REASONING_MANDATORY, get_settings, reasoning_for


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "s3")
    monkeypatch.setenv("STANCE_MODEL", "acme/fast")
    monkeypatch.setenv("CANARY_MIN_CREDITS_USD", "5")
    s = get_settings()
    assert s.session_secret == "s3"
    assert s.models()["stance"] == "acme/fast"
    assert s.canary_min_credits_usd == 5.0


def test_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("STANCE_MODEL", "DRAFT_MODEL", "CLASSIFY_MODEL", "JUDGE_MODEL", "RECHECK_MODEL"):
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


def test_the_recheck_model_defaults_to_the_stance_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANCE_MODEL", "acme/fast")
    monkeypatch.delenv("RECHECK_MODEL", raising=False)
    assert get_settings().models()["recheck"] == "acme/fast"
    monkeypatch.setenv("RECHECK_MODEL", "acme/other")
    assert get_settings().models()["recheck"] == "acme/other"


# The model pool (spec 6.14): cheap Chinese or open-weight models on OpenRouter with structured outputs.
POOL = ("deepseek/", "qwen/", "z-ai/", "moonshotai/", "minimax/", "xiaomi/", "openai/gpt-oss-")


def test_defaults_come_from_the_model_pool_and_the_judge_is_from_another_family() -> None:
    assert all(model.startswith(POOL) for model in DEFAULT_MODELS.values())
    assert DEFAULT_MODELS["judge"].split("/")[0] != DEFAULT_MODELS["draft"].split("/")[0]


def test_interim_defaults_avoid_a_provider_that_ignores_the_schema() -> None:
    # qwen3.5-flash's only provider does not enforce strict json_schema; interim until the bench.
    assert {DEFAULT_MODELS[s] for s in ("stance", "classify", "recheck")} == {"deepseek/deepseek-v4-flash"}


def test_mandatory_reasoning_set_matches_the_catalog_snapshot() -> None:
    # Snapshot of OpenRouter /models for the bench candidates (2026-10-05); refresh it when the pool changes.
    snap = json.loads((Path(__file__).parent / "openrouter_catalog_snapshot.json").read_text())
    mandatory = {m for m, e in snap.items() if (e["reasoning"] or {}).get("mandatory")}
    assert mandatory == REASONING_MANDATORY
    assert all("low" in snap[m]["reasoning"]["supported_efforts"] for m in mandatory)
    assert all("reasoning" in e["supported_parameters"] for e in snap.values())


def test_off_means_lowest_effort_only_where_reasoning_is_mandatory() -> None:
    assert reasoning_for("stance", "anthropic/claude-sonnet-5.5") == {"effort": "low"}
    assert reasoning_for("stance", "deepseek/deepseek-v4-flash") == {"enabled": False}  # keys unchanged
    assert reasoning_for("draft", "openai/gpt-oss-120b") is None  # the model's default stays the default

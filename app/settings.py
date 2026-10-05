"""All configuration comes from environment variables. Nothing secret has a default."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Every default comes from the model pool (spec 6.14): cheap Chinese or open-weight models on OpenRouter
# that support structured outputs. These are starting values; Plan 2's model bench replaces them with
# measured picks. Claude Sonnet 5.5 runs only in the bench, as the quality reference, and is never a
# default. The judge's family differs from the drafter's: when the drafter is a Qwen model, the judge is
# moonshotai/kimi-k2.5.
# Interim: stance, classify and recheck left qwen/qwen3.5-flash-02-23, whose only provider downgrades strict
# json_schema to json_object and does not enforce the schema (first live recording, 2026-10-05).
DEFAULT_MODELS = {
    "stance": "deepseek/deepseek-v4-flash",
    "draft": "deepseek/deepseek-v4-flash",
    "classify": "deepseek/deepseek-v4-flash",
    "judge": "qwen/qwen3.7-plus",
    "recheck": "deepseek/deepseek-v4-flash",  # the stance prompt on a visitor's statement
}


# OpenRouter's unified `reasoning` parameter, per step; None sends nothing (the model's default). DeepSeek and
# Qwen3 thinking is on/off only, so any effort level means "on": off is the only way to cut it. Thinking spent
# 700-2200 tokens on short structured judgements and overflowed the judge's max_tokens (Ruling 7); the bench
# measures any quality cost, and a step can be switched back on here. Part of every recording key.
REASONING: dict[str, dict[str, bool | str] | None] = {
    "stance": {"enabled": False},
    "classify": {"enabled": False},
    "recheck": {"enabled": False},
    "judge": {"enabled": False},
    "canary": {"enabled": False},
    "draft": None,
}

# Models whose catalog entry says reasoning.mandatory (OpenRouter /models, 2026-10-05): they answer 400
# "Reasoning is mandatory for this endpoint and cannot be disabled" to {"enabled": False}, so "off" means
# their lowest effort.
# tests/test_settings.py pins this set to tests/openrouter_catalog_snapshot.json.
REASONING_MANDATORY = frozenset({"anthropic/claude-sonnet-5.5", "openai/gpt-oss-120b", "z-ai/glm-5.3-flash"})
LOWEST_EFFORT: dict[str, bool | str] = {"effort": "low"}  # every model in REASONING_MANDATORY lists "low"


def reasoning_for(step: str, model: str) -> dict[str, bool | str] | None:
    setting = REASONING[step]
    return LOWEST_EFFORT if setting == {"enabled": False} and model in REASONING_MANDATORY else setting


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    database_url: str = ""
    session_secret: str = ""
    cron_secret: str = ""
    openrouter_api_key: str = ""
    stance_model: str = DEFAULT_MODELS["stance"]
    draft_model: str = DEFAULT_MODELS["draft"]
    classify_model: str = DEFAULT_MODELS["classify"]
    judge_model: str = DEFAULT_MODELS["judge"]
    recheck_model: str = ""  # empty: the stance model
    canary_min_credits_usd: float = 2.0

    def models(self) -> dict[str, str]:
        return {
            "stance": self.stance_model,
            "draft": self.draft_model,
            "classify": self.classify_model,
            "judge": self.judge_model,
            "recheck": self.recheck_model or self.stance_model,
        }


def get_settings() -> Settings:
    # ponytail: re-reads the environment on every call (microseconds); keeps tests free to change env vars.
    # Cache it only if profiling ever shows it.
    return Settings()

"""All configuration comes from environment variables. Nothing secret has a default."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Every default comes from the model pool (spec 6.14): cheap Chinese or open-weight models on OpenRouter
# that support structured outputs. These are starting values; Plan 2's model bench replaces them with
# measured picks. Claude Sonnet 5.5 runs only in the bench, as the quality reference, and is never a
# default. The judge's family differs from the drafter's: when the drafter is a Qwen model, the judge is
# moonshotai/kimi-k2.5.
DEFAULT_MODELS = {
    "stance": "qwen/qwen3.5-flash-02-23",
    "draft": "deepseek/deepseek-v4-flash",
    "classify": "qwen/qwen3.5-flash-02-23",
    "judge": "qwen/qwen3.7-plus",
    "recheck": "qwen/qwen3.5-flash-02-23",  # the stance prompt on a visitor's statement
}


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

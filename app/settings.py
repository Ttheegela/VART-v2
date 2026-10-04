"""All configuration comes from environment variables. Nothing secret has a default."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Provisional defaults (PriorPath-proven model IDs); Plan 2's model bench replaces them with measured choices.
DEFAULT_MODELS = {
    "stance": "google/gemini-2.5-flash-lite",
    "draft": "deepseek/deepseek-v4-flash",
    "classify": "google/gemini-2.5-flash-lite",
    "judge": "google/gemini-2.5-flash",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = ""
    session_secret: str = ""
    cron_secret: str = ""
    openrouter_api_key: str = ""
    stance_model: str = DEFAULT_MODELS["stance"]
    draft_model: str = DEFAULT_MODELS["draft"]
    classify_model: str = DEFAULT_MODELS["classify"]
    judge_model: str = DEFAULT_MODELS["judge"]
    canary_min_credits_usd: float = 2.0

    def models(self) -> dict[str, str]:
        return {
            "stance": self.stance_model,
            "draft": self.draft_model,
            "classify": self.classify_model,
            "judge": self.judge_model,
        }


def get_settings() -> Settings:
    # ponytail: re-reads the environment on every call (microseconds); keeps tests free to change env vars.
    # Cache it only if profiling ever shows it.
    return Settings()

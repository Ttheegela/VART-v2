"""Daily check that each configured model still answers and the OpenRouter key still has credit, so a retired
model ID or an empty balance shows up in /api/health (and UptimeRobot's email) before a visitor finds it."""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.models import CanaryRun
from app.llm.client import OPENROUTER_BASE_URL, LLMClient, LLMError, build_request, complete_model
from app.settings import Settings

PROMPT_VERSION = "canary@1"


class CanaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


def remaining_credits(http: httpx.Client, api_key: str) -> float | None:
    """This key's remaining credit when the key has a limit (set one in OpenRouter); otherwise None."""
    try:
        r = http.get(f"{OPENROUTER_BASE_URL}/key", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    data = body.get("data") if isinstance(body, dict) else None
    value = data.get("limit_remaining") if isinstance(data, dict) else None
    return float(value) if isinstance(value, int | float) else None


def run_canary(
    session: Session, client: LLMClient | None, http: httpx.Client, settings: Settings
) -> CanaryRun:
    detail: dict[str, Any] = {"models": {}, "credits_usd": None}
    ok = True
    if client is None:
        detail["error"] = "OPENROUTER_API_KEY is not set"
        ok = False
    else:
        for model in sorted(set(settings.models().values())):
            req = build_request(
                "canary",
                model,
                PROMPT_VERSION,
                "Reply with JSON only.",
                'Return {"ok": true}.',
                CanaryOut,
                2000,  # reasoning models spend max_tokens on thinking; 200 ended in finish_reason=length
            )
            try:
                complete_model(client, req, CanaryOut)
                detail["models"][model] = "ok"
            except LLMError as exc:
                detail["models"][model] = str(exc)[:200]
                ok = False
        credits = remaining_credits(http, settings.openrouter_api_key)
        detail["credits_usd"] = credits
        if credits is not None and credits < settings.canary_min_credits_usd:
            ok = False
    row = CanaryRun(ok=ok, detail=detail)
    session.add(row)
    session.commit()
    session.refresh(row)  # commit expires it; callers read it after their session may be closed
    return row

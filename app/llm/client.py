"""OpenRouter chat completions with strict JSON-schema outputs. Recording and replay live in recorder.py."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
from openai import APIError, OpenAI
from pydantic import BaseModel, ValidationError

from app.observability import Step, trace_llm
from app.settings import get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMError(Exception):
    """The model call failed or returned something unusable. Callers degrade; a request never crashes."""


@dataclass(frozen=True)
class LLMRequest:
    step: Step
    model: str
    prompt_version: str
    system: str
    user: str
    schema_name: str
    schema: dict[str, Any]
    max_tokens: int = 1200

    def key(self) -> str:
        payload = json.dumps(
            [self.model, self.prompt_version, self.system, self.user, self.schema_name, self.schema],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class LLMClient(Protocol):
    def complete(self, req: LLMRequest) -> LLMResult: ...


def _assert_strict(schema: dict[str, Any], where: str = "$") -> None:
    """Strict structured outputs need every object closed and every property required."""
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{where}: set model_config = ConfigDict(extra='forbid')")
        missing = set(schema.get("properties", {})) - set(schema.get("required", []))
        if missing:
            raise ValueError(f"{where}: fields need no default for strict outputs: {sorted(missing)}")
    for key in ("properties", "$defs"):
        for name, sub in schema.get(key, {}).items():
            _assert_strict(sub, f"{where}.{name}")
    if isinstance(schema.get("items"), dict):
        _assert_strict(schema["items"], f"{where}[]")
    for sub in schema.get("anyOf", []):
        _assert_strict(sub, where)


def build_request(
    step: Step,
    model: str,
    prompt_version: str,
    system: str,
    user: str,
    out: type[BaseModel],
    max_tokens: int = 1200,
) -> LLMRequest:
    schema = out.model_json_schema()
    _assert_strict(schema)
    return LLMRequest(step, model, prompt_version, system, user, out.__name__, schema, max_tokens)


def complete_model[M: BaseModel](client: LLMClient, req: LLMRequest, out: type[M]) -> M:
    result = client.complete(req)
    try:
        return out.model_validate_json(result.text)
    except ValidationError as exc:
        raise LLMError(f"{req.step}: output did not match {req.schema_name}") from exc


def _usage(response: Any) -> tuple[int, int, float | None]:
    u = getattr(response, "usage", None)
    if u is None:
        return 0, 0, None
    cost = getattr(u, "cost", None)
    return int(u.prompt_tokens or 0), int(u.completion_tokens or 0), float(cost) if cost is not None else None


class OpenRouterClient:
    def __init__(
        self, api_key: str, *, timeout: float = 60.0, http_client: httpx.Client | None = None
    ) -> None:
        # openai 3.x types http_client as httpx2.Client but still accepts a plain httpx.Client at runtime
        # (tests pass one with httpx.MockTransport); the cast keeps mypy quiet under any openai version.
        self._client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
            max_retries=0,
            http_client=cast(Any, http_client),
        )

    def complete(self, req: LLMRequest) -> LLMResult:
        meta: dict[str, str | int | float | bool] = {"prompt_version": req.prompt_version, "step": req.step}
        with trace_llm(req.step, model=req.model, kind=req.step, metadata=meta) as span:
            try:
                response = self._client.chat.completions.create(
                    model=req.model,
                    messages=[
                        {"role": "system", "content": req.system},
                        {"role": "user", "content": req.user},
                    ],
                    max_tokens=req.max_tokens,
                    temperature=0,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": req.schema_name, "strict": True, "schema": req.schema},
                    },
                    extra_body={"usage": {"include": True}},
                )
            except APIError as exc:  # connection errors, timeouts and HTTP status errors
                raise LLMError(f"{req.step}: {type(exc).__name__}") from exc
            choice = response.choices[0]
            tokens_in, tokens_out, cost = _usage(response)
            span.end(
                {"ok": choice.finish_reason == "stop", "finish_reason": str(choice.finish_reason)},
                {"input": tokens_in, "output": tokens_out},
            )
            if choice.finish_reason != "stop":  # truncated or filtered
                raise LLMError(f"{req.step}: finish_reason={choice.finish_reason}")
            return LLMResult(choice.message.content or "", tokens_in, tokens_out, cost)


def default_client() -> LLMClient | None:
    key = get_settings().openrouter_api_key
    return OpenRouterClient(key) if key else None

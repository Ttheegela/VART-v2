import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.client import LLMError, OpenRouterClient, build_request, complete_model
from tests.fakes import FakeLLM


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    note: str | None


def _reply(content: str, finish: str = "stop", cost: float | None = 0.0001) -> dict[str, Any]:
    usage: dict[str, Any] = {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": "acme/fast",
        "choices": [
            {"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}
        ],
        "usage": usage,
    }


def _client(handler: Any) -> OpenRouterClient:
    return OpenRouterClient("test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _req() -> Any:
    return build_request("stance", "acme/fast", "stance@p1", "system text", "user text", Out)


def test_sends_a_strict_json_schema_request() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_reply('{"ok": true, "note": null}'))

    result = _client(handler).complete(_req())
    assert seen["model"] == "acme/fast" and seen["temperature"] == 0
    fmt = seen["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "Out"
    assert seen["usage"] == {"include": True}
    assert result.text == '{"ok": true, "note": null}'
    assert (result.input_tokens, result.output_tokens, result.cost_usd) == (12, 3, 0.0001)


def test_truncated_reply_is_an_error() -> None:
    client = _client(lambda r: httpx.Response(200, json=_reply('{"ok": tr', finish="length")))
    with pytest.raises(LLMError, match="finish_reason"):
        client.complete(_req())


def test_http_errors_are_llm_errors_and_never_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    with pytest.raises(LLMError):
        _client(handler).complete(_req())
    assert len(calls) == 1


def test_timeouts_are_llm_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError):
        _client(handler).complete(_req())


def test_complete_model_parses_and_rejects_wrong_shapes() -> None:
    assert complete_model(FakeLLM(['{"ok": true, "note": "x"}']), _req(), Out) == Out(ok=True, note="x")
    with pytest.raises(LLMError, match="Out"):
        complete_model(FakeLLM(['{"ok": "maybe"}']), _req(), Out)
    with pytest.raises(LLMError):
        complete_model(FakeLLM(["not json"]), _req(), Out)


def test_build_request_rejects_loose_schemas() -> None:
    class WithDefault(BaseModel):
        model_config = ConfigDict(extra="forbid")
        ok: bool = True

    class Open(BaseModel):
        ok: bool

    for loose in (WithDefault, Open):
        with pytest.raises(ValueError):
            build_request("stance", "m", "p", "s", "u", loose)


def test_nested_models_must_be_strict_too() -> None:
    class Inner(BaseModel):
        ok: bool

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        items: list[Inner]

    with pytest.raises(ValueError):
        build_request("stance", "m", "p", "s", "u", Outer)


def test_request_key_is_stable_and_changes_with_the_prompt_version() -> None:
    a = build_request("stance", "m", "p1", "s", "u", Out)
    b = build_request("stance", "m", "p1", "s", "u", Out)
    c = build_request("stance", "m", "p2", "s", "u", Out)
    assert a.key() == b.key() != c.key()

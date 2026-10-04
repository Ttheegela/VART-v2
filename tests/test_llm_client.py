import json
from typing import Annotated, Any, Literal

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, create_model

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


@pytest.mark.parametrize("status", [402, 429, 500])  # the SDK itself retries 429 and 5xx, never 402
def test_http_errors_are_llm_errors_and_never_retried(status: int) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "Insufficient credits"}})

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


def _json(body: Any) -> Any:
    return lambda request: httpx.Response(200, json=body)


def _bytes(content: bytes, content_type: str) -> Any:
    return lambda request: httpx.Response(200, content=content, headers={"content-type": content_type})


def _with(**changes: Any) -> dict[str, Any]:
    return {**_reply('{"ok": true, "note": null}'), **changes}


# Every way a 200 can come back unusable. Callers (the canary, the pipeline) catch only LLMError.
UNUSABLE = {
    "error body and no choices": _json({"error": {"message": "Provider returned error", "code": 502}}),
    "choices is empty": _json(_with(choices=[])),
    "choices is null": _json(_with(choices=None)),
    "choices is an object": _json(_with(choices={"a": 1})),
    "choice is null": _json(_with(choices=[None])),
    "message is null": _json(_with(choices=[{"index": 0, "finish_reason": "stop", "message": None}])),
    "html page": _bytes(b"<html>bad gateway</html>", "text/html"),
    "empty body": _bytes(b"", "text/plain"),
    "204 no content": lambda request: httpx.Response(204),
    "truncated json": _bytes(b'{"choices": [', "application/json"),
    "invalid utf-8": _bytes(b'{"a": "' + bytes([0xFF]) + b'"}', "application/json"),
    "usage tokens are not numbers": _json(_with(usage={"prompt_tokens": "abc", "completion_tokens": 1})),
    "usage cost is not a number": _json(
        _with(usage={"prompt_tokens": 1, "completion_tokens": 1, "cost": "abc"})
    ),
    "usage is not an object": _json(_with(usage="n/a")),
}


@pytest.mark.parametrize("handler", UNUSABLE.values(), ids=UNUSABLE.keys())
def test_an_unusable_response_is_an_llm_error(handler: Any) -> None:
    with pytest.raises(LLMError, match="unusable response"):
        _client(handler).complete(_req())


def test_a_prompt_that_cannot_be_encoded_is_an_llm_error() -> None:
    lone_surrogate = chr(0xD800)  # what a broken PDF extraction can leave behind
    req = build_request("stance", "acme/fast", "stance@p1", "system text", "bad " + lone_surrogate, Out)
    with pytest.raises(LLMError, match="unusable response"):
        _client(_json(_reply("{}"))).complete(req)


def test_a_missing_cost_or_usage_is_none_and_zero_not_a_failure() -> None:
    no_cost = _client(_json(_reply('{"ok": true, "note": null}', cost=None))).complete(_req())
    assert (no_cost.input_tokens, no_cost.output_tokens, no_cost.cost_usd) == (12, 3, None)
    body = _reply('{"ok": true, "note": null}')
    del body["usage"]
    no_usage = _client(_json(body)).complete(_req())
    assert (no_usage.input_tokens, no_usage.output_tokens, no_usage.cost_usd) == (0, 0, None)


def test_item_id_is_trace_only_and_never_changes_the_key() -> None:
    plain = build_request("stance", "m", "p1", "s", "u", Out)
    tagged = build_request("stance", "m", "p1", "s", "u", Out, item_id="i-1")
    assert plain.item_id is None and tagged.item_id == "i-1"
    assert plain.key() == tagged.key()


class Golden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    note: str | None


def test_the_request_key_is_pinned() -> None:
    # Every recording is stored under this key. If this fails, the key recipe or the JSON schema that pydantic
    # emits changed (a pydantic upgrade can do that), which silently re-keys every recording. Updating the
    # digest means re-recording evals.
    req = build_request(
        "stance",
        "acme/fast",
        "stance@p1",
        "You answer security questionnaires.",
        "Is data encrypted at rest?",
        Golden,
    )
    assert req.key() == "f161dab50867e96edd9fb63aeaafba56dba94af3f7be62649f1d67e979bfb103", json.dumps(
        req.schema, sort_keys=True
    )


class OptionA(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["a"]


class OptionB(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["b"]


class WithTuple(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pair: tuple[int, str]


class WithTaggedUnion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick: Annotated[OptionA | OptionB, Field(discriminator="kind")]


class WithPlainUnion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick: OptionA | OptionB


@pytest.mark.parametrize(("model", "keyword"), [(WithTuple, "prefixItems"), (WithTaggedUnion, "oneOf")])
def test_build_request_rejects_keywords_that_strict_providers_refuse(
    model: type[BaseModel], keyword: str
) -> None:
    with pytest.raises(ValueError, match=keyword):
        build_request("stance", "m", "p", "s", "u", model)


def test_a_plain_union_of_strict_models_is_accepted() -> None:
    assert build_request("stance", "m", "p", "s", "u", WithPlainUnion).schema_name == "WithPlainUnion"


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[T]


def test_build_request_rejects_schema_names_a_provider_would_400() -> None:
    assert Page[Item].__name__ == "Page[Item]"  # what pydantic calls a parametrised generic
    with pytest.raises(ValueError, match="schema name"):
        build_request("stance", "m", "p", "s", "u", Page[Item])
    strict = ConfigDict(extra="forbid")
    with pytest.raises(ValueError, match="schema name"):
        build_request("stance", "m", "p", "s", "u", create_model("A" * 65, __config__=strict, ok=(bool, ...)))
    longest = create_model("A" * 64, __config__=strict, ok=(bool, ...))
    assert build_request("stance", "m", "p", "s", "u", longest).schema_name == "A" * 64


def test_error_paths_name_the_offending_definition() -> None:
    class Inner(BaseModel):
        ok: bool

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        items: list[Inner]

    with pytest.raises(ValueError, match=r"\$defs\.Inner"):
        build_request("stance", "m", "p", "s", "u", Outer)

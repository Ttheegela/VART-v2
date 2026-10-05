import json
from types import SimpleNamespace
from typing import Annotated, Any, Literal

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, create_model

from app.llm.client import LLMError, OpenRouterClient, _plain, build_request, complete_model
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
    # only providers that honour every parameter we send (strict json_schema among them)
    assert seen["provider"] == {"require_parameters": True}
    assert result.text == '{"ok": true, "note": null}'
    assert (result.input_tokens, result.output_tokens, result.cost_usd) == (12, 3, 0.0001)


def test_every_structured_request_says_json() -> None:
    # A provider that downgrades json_schema to json_object (Alibaba) refuses messages without "json".
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_reply('{"ok": true, "note": null}'))

    _client(handler).complete(_req())
    assert "response_format" in seen
    assert "json" in " ".join(m["content"] for m in seen["messages"]).lower()


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


def _with_raw_tokens(literal: str) -> bytes:
    # httpx refuses to serialise infinity, so the number goes into the JSON text by hand
    body = json.dumps(_with(usage={"prompt_tokens": "TOKENS", "completion_tokens": 1}))
    return body.replace('"TOKENS"', literal).encode()


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
    "usage tokens overflow to infinity": _bytes(_with_raw_tokens("1e999"), "application/json"),
    "absurdly nested json": _bytes(b"[" * 100_000, "application/json"),
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


GOLDEN_KEY = "8fa38bbee92e2d7899e7716a81c34c6b07c11dfe6a090e05e0dea9fd0837e5a2"


def _golden(user: str = "Is data encrypted at rest?") -> Any:
    return build_request(
        "stance", "acme/fast", "stance@p1", "You answer security questionnaires.", user, Golden
    )


def test_the_request_key_is_pinned() -> None:
    # Every recording is stored under this key. If this fails, the key recipe or the JSON schema that pydantic
    # emits changed (a pydantic upgrade can do that), which silently re-keys every recording. Updating the
    # digest means re-recording evals.
    assert _golden().key() == GOLDEN_KEY, json.dumps(_golden().schema, sort_keys=True)


def test_a_lone_surrogate_in_a_prompt_still_gets_its_own_key() -> None:
    # A broken PDF extraction can leave one behind. key() must not raise, valid text must key exactly as
    # before, and the encoding must not be lossy (replace or ignore would make prompts share one key).
    assert _golden().key() == GOLDEN_KEY
    first = _golden("bad " + chr(0xD800)).key()
    second = _golden("bad " + chr(0xD801)).key()
    assert len(first) == 64 and first != second
    lossy = {_golden(f"bad {tail}").key() for tail in ("", "?", chr(0xFFFD))}
    assert {first, second}.isdisjoint(lossy)


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


GOLDEN_KEY_NON_ASCII = "48800d90065cb9de4b06b22e74ff554cedbb3ba3770e652987f04400f667ab8e"


def test_a_non_ascii_request_key_is_pinned() -> None:
    # Pins ensure_ascii=False in key(): flipping it re-keys every recording that holds a curly quote or an
    # accented letter, and the ASCII golden key above would not notice.
    user = (
        "Wird der Zugriff viertelj\N{LATIN SMALL LETTER A WITH DIAERESIS}hrlich "
        "gepr\N{LATIN SMALL LETTER U WITH DIAERESIS}ft? \N{LEFT DOUBLE QUOTATION MARK}Ja"
        "\N{RIGHT DOUBLE QUOTATION MARK} \N{EM DASH} caf\N{LATIN SMALL LETTER E WITH ACUTE} \N{CHECK MARK}"
    )
    assert _golden(user).key() == GOLDEN_KEY_NON_ASCII


@pytest.mark.parametrize(
    ("raw", "cost"),
    [("1e999", None), ("-1e999", None), ("NaN", None), ("-0.5", None), ("0.0", 0.0)],  # free models cost 0
)
def test_a_cost_is_kept_only_when_finite_non_negative(raw: str, cost: float | None) -> None:
    body = json.dumps(_reply('{"ok": true, "note": null}', cost=123.0)).replace("123.0", raw).encode()
    result = _client(_bytes(body, "application/json")).complete(_req())
    assert result.cost_usd == cost and result.text == '{"ok": true, "note": null}'


def test_a_call_reports_its_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the client's clock: the trace span reads time.monotonic too.
    monkeypatch.setattr("app.llm.client.time", SimpleNamespace(monotonic=iter([10.0, 10.25]).__next__))
    result = _client(_json(_reply('{"ok": true, "note": null}'))).complete(_req())
    assert result.latency_ms == 250


def test_a_strange_finish_reason_is_not_echoed_raw() -> None:
    client = _client(_json(_reply("{}", finish="Content<script>Filter")))
    with pytest.raises(LLMError, match=r"finish_reason=contentscriptfilter$"):
        client.complete(_req())


@pytest.mark.parametrize(
    ("value", "plain"),
    [
        ("", "unknown"),
        ("\N{CJK UNIFIED IDEOGRAPH-505C}\N{CJK UNIFIED IDEOGRAPH-6B62}", "unknown"),
        ("abcdefghij" * 5, "abcdefghij" * 2),
        (None, "none"),
    ],
)
def test_plain_keeps_only_a_short_lowercase_word(value: object, plain: str) -> None:
    assert _plain(value) == plain


@pytest.mark.parametrize("handler", UNUSABLE.values(), ids=UNUSABLE.keys())
def test_an_unusable_response_keeps_its_cause(handler: Any) -> None:
    with pytest.raises(LLMError) as caught:
        _client(handler).complete(_req())
    assert isinstance(caught.value.__cause__, Exception) and not isinstance(caught.value.__cause__, LLMError)


def test_requests_differing_only_in_max_tokens_have_different_keys() -> None:
    a = build_request("stance", "m", "stance@p1", "s", "u", OptionA, 3000)
    b = build_request("stance", "m", "stance@p1", "s", "u", OptionA, 500)
    assert a.key() != b.key()

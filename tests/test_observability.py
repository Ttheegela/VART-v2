import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app import observability
from app.llm.client import LLMError, OpenRouterClient, build_request
from app.observability import flush, has_pending, trace_llm


class FakeObs:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self.ended = False

    def update(self, **kw: Any) -> None:
        self.updates.append(kw)

    def end(self) -> None:
        self.ended = True


class FakeLangfuse:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.obs = FakeObs()
        self.flushed = 0

    def start_observation(self, **kw: Any) -> FakeObs:
        self.started.append(kw)
        return self.obs

    def flush(self) -> None:
        self.flushed += 1


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeLangfuse:
    fl = FakeLangfuse()
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(observability, "_factory", lambda: fl)
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_pending", 0)
    monkeypatch.setattr(observability, "_warned", False)
    monkeypatch.setattr(observability, "_flusher", None)
    return fl


def test_without_keys_tracing_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    def boom() -> None:
        raise AssertionError("must not build a client")

    monkeypatch.setattr(observability, "_factory", boom)
    with trace_llm("stance", model="m", kind="stance", metadata={}) as span:
        span.end({"ok": True})


def test_only_allow_listed_metadata_leaves_the_app(fake: FakeLangfuse) -> None:
    meta = {"prompt_version": "stance@p1", "item_id": "i-1", "question": "SECRET QUESTION"}
    with trace_llm("stance", model="m", kind="stance", metadata=meta) as span:
        span.end({"ok": True, "answer": "SECRET ANSWER"}, {"input": 1, "output": 2})
    sent = fake.started[0]["metadata"]
    assert sent == {"prompt_version": "stance@p1", "item_id": "i-1", "kind": "stance"}
    out = fake.obs.updates[0]["output"]
    assert "answer" not in out and out["ok"] is True and "latency_ms" in out


def test_sdk_failures_never_reach_the_caller(fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(**kw: Any) -> None:
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(fake, "start_observation", broken)
    with trace_llm("draft", model="m", kind="draft", metadata={}) as span:
        span.end({"ok": True})


def test_flush_delivers_pending_spans(fake: FakeLangfuse) -> None:
    with trace_llm("draft", model="m", kind="draft", metadata={}) as span:
        span.end({"ok": True})
    assert has_pending()
    flush()
    assert fake.flushed == 1 and not has_pending()


def test_sdk_failures_are_logged_once_and_without_details(
    fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(**kw: Any) -> None:
        raise RuntimeError("secret detail from the sdk")

    monkeypatch.setattr(fake, "start_observation", broken)
    with caplog.at_level("WARNING", logger="app.observability"):
        for _ in range(2):
            with trace_llm("draft", model="m", kind="draft", metadata={}) as span:
                span.end({"ok": True})
    logged = [r.getMessage() for r in caplog.records if r.name == "app.observability"]
    assert logged == ["langfuse tracing failed (further failures suppressed): RuntimeError"]


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


GOOD = {
    "id": "gen-1",
    "object": "chat.completion",
    "created": 0,
    "model": "acme/fast",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"ok": true}'}}
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
}


def _call(handler: Any, item_id: str | None = None) -> None:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    req = build_request(
        "stance", "acme/fast", "stance@p1", "SECRET SYSTEM", "SECRET USER", Reply, item_id=item_id
    )
    OpenRouterClient("k", http_client=http).complete(req)


def test_item_id_reaches_the_trace_only_when_set(fake: FakeLangfuse) -> None:
    _call(lambda request: httpx.Response(200, json=GOOD), item_id="i-9")
    _call(lambda request: httpx.Response(200, json=GOOD))
    with_id, without_id = (started["metadata"] for started in fake.started)
    assert with_id == {"prompt_version": "stance@p1", "step": "stance", "kind": "stance", "item_id": "i-9"}
    assert without_id == {"prompt_version": "stance@p1", "step": "stance", "kind": "stance"}
    assert fake.obs.updates[0]["output"]["ok"] is True
    assert "SECRET" not in json.dumps([fake.started, fake.obs.updates])


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("SECRET DETAIL", request=request)


def _message_null(request: httpx.Request) -> httpx.Response:
    choice = {"index": 0, "finish_reason": "stop", "message": None}
    return httpx.Response(200, json={**GOOD, "choices": [choice]})


@pytest.mark.parametrize(
    ("handler", "error_type"),
    [
        (lambda request: httpx.Response(402, json={"error": {"message": "SECRET DETAIL"}}), "APIStatusError"),
        (_timeout, "APITimeoutError"),
        (_message_null, "AttributeError"),
    ],
    ids=["402", "timeout", "message null"],
)
def test_a_failed_call_ends_its_span_not_ok_with_the_underlying_error_type(
    fake: FakeLangfuse, handler: Any, error_type: str
) -> None:
    with pytest.raises(LLMError):
        _call(handler)
    assert len(fake.obs.updates) == 1
    out = fake.obs.updates[0]["output"]
    assert out["ok"] is False and out["error_type"] == error_type
    assert "SECRET" not in json.dumps([fake.started, fake.obs.updates])

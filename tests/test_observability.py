from typing import Any

import pytest

from app import observability
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

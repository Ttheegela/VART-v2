from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.client import LLMError, build_request
from app.llm.recorder import RecordingClient, ReplayClient, ReplayMiss
from tests.fakes import FakeLLM


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


REQ = build_request("draft", "acme/fast", "draft@p1", "s", "u", Out)
OTHER = build_request("draft", "acme/fast", "draft@p1", "s", "different user text", Out)


def test_recording_calls_the_model_once_per_request(tmp_path: Path) -> None:
    inner = FakeLLM(['{"ok": true}'])
    rec = RecordingClient(inner, tmp_path / "r.jsonl")
    assert rec.complete(REQ).text == rec.complete(REQ).text == '{"ok": true}'
    assert len(inner.requests) == 1
    assert len((tmp_path / "r.jsonl").read_text().splitlines()) == 1


def test_recording_resumes_from_an_existing_file(tmp_path: Path) -> None:
    RecordingClient(FakeLLM(['{"ok": true}']), tmp_path / "r.jsonl").complete(REQ)
    again = RecordingClient(FakeLLM([]), tmp_path / "r.jsonl")  # would raise if it called the model
    assert again.complete(REQ).text == '{"ok": true}'


def test_replay_returns_recordings_and_fails_loudly_on_a_miss(tmp_path: Path) -> None:
    RecordingClient(FakeLLM(['{"ok": false}']), tmp_path / "r.jsonl").complete(REQ)
    replay = ReplayClient(tmp_path / "r.jsonl")
    assert replay.complete(REQ).text == '{"ok": false}'
    with pytest.raises(ReplayMiss, match="draft"):
        replay.complete(OTHER)


def test_a_replay_miss_is_an_llm_error() -> None:
    assert issubclass(ReplayMiss, LLMError)

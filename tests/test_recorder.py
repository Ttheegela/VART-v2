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


def test_recordings_survive_unicode_line_separators(tmp_path: Path) -> None:
    # U+2028, U+2029 and U+0085 stay raw in the JSON the recorder writes (ensure_ascii=False), but
    # str.splitlines() treats them as line breaks: a row was cut in half and the whole file became unreadable.
    text = "a" + chr(0x2028) + "b" + chr(0x2029) + "c" + chr(0x85) + "d"
    path = tmp_path / "r.jsonl"
    RecordingClient(FakeLLM([text]), path).complete(REQ)
    written = path.read_text(encoding="utf-8")
    assert all(ch in written for ch in (chr(0x2028), chr(0x2029), chr(0x85)))  # the premise: raw in the file
    assert ReplayClient(path).complete(REQ).text == text
    assert RecordingClient(FakeLLM([]), path).complete(REQ).text == text

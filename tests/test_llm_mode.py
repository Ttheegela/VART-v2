from pathlib import Path

import pytest

from app.api.deps import get_llm
from app.llm.recorder import ReplayClient


def test_replay_mode_serves_the_recording(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text("")
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("LLM_RECORDING", str(path))
    assert isinstance(get_llm(), ReplayClient)


def test_only_live_mode_runs_on_vercel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("LLM_RECORDING", str(tmp_path / "r.jsonl"))
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="live"):
        get_llm()


def test_live_mode_without_a_key_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert get_llm() is None

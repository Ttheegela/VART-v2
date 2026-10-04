"""Record and replay model outputs so tests, evals and CI run without keys or network.

A recording is JSONL: one line per model call, keyed by LLMRequest.key(). Replay never calls a model; a
missing key raises ReplayMiss, so a changed prompt fails loudly instead of silently going live."""

import json
import threading
from pathlib import Path
from typing import Any

from app.llm.client import LLMClient, LLMError, LLMRequest, LLMResult


class ReplayMiss(LLMError):
    pass


def _load(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if path.exists():
        # Not splitlines(): it also splits on U+2028, U+2029 and U+0085, which json.dumps(ensure_ascii=False)
        # writes raw, so a row containing one would be cut in half.
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                row = json.loads(line)
                rows[row["key"]] = row
    return rows


def _result(row: dict[str, Any]) -> LLMResult:
    return LLMResult(row["text"], row["input_tokens"], row["output_tokens"], row["cost_usd"])


class ReplayClient:
    def __init__(self, path: Path) -> None:
        self._rows = _load(path)

    def complete(self, req: LLMRequest) -> LLMResult:
        row = self._rows.get(req.key())
        if row is None:
            raise ReplayMiss(f"{req.step}: no recording for key {req.key()[:12]} ({req.prompt_version})")
        return _result(row)


class RecordingClient:
    def __init__(self, inner: LLMClient, path: Path) -> None:
        self._inner = inner
        self._path = path
        self._rows = _load(path)
        self._lock = threading.Lock()  # stance calls run in parallel threads

    def complete(self, req: LLMRequest) -> LLMResult:
        key = req.key()
        with self._lock:
            if key in self._rows:
                return _result(self._rows[key])
        result = self._inner.complete(req)
        row = {
            "key": key,
            "step": req.step,
            "model": req.model,
            "prompt_version": req.prompt_version,
            "text": result.text,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
        }
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            self._rows[key] = row
        return result

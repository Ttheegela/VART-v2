from datetime import date

import pytest

from app.llm.client import LLMRequest, LLMResult, build_request
from evals.bench import REFERENCE, Usage, judge_for, judges_for, main, markdown, usable
from evals.judge import JudgeOut


def test_only_catalogued_models_with_structured_outputs_are_benched(capsys) -> None:  # type: ignore[no-untyped-def]
    known = {"a/one": ["structured_outputs", "tools"], "b/two": ["tools"], "c/three": ["response_format"]}
    assert usable(["a/one", "b/two", "c/three", "d/four"], known) == ["a/one", "c/three"]
    out = capsys.readouterr().out
    assert "skip b/two: no structured outputs" in out and "skip d/four: not in OpenRouter's catalog" in out


def test_usage_adds_up_cost_and_latency() -> None:
    class Inner:
        def complete(self, req: LLMRequest) -> LLMResult:
            return LLMResult("{}", 1, 1, 0.25, 800)

    usage = Usage(Inner())
    req = build_request("stance", "m", "p", "s", "u", JudgeOut)
    usage.complete(req)
    usage.complete(req)
    assert usage.calls == [(0.25, 800), (0.25, 800)]


def test_the_bench_table_has_one_row_per_model() -> None:
    text = markdown("stance", "dev", [{"model": "a/one", "label_accuracy": 0.9, "cost_usd": 0.1}])
    assert f"# Model bench: stance (dev pack, {date.today().isoformat()})" in text
    assert "| model | label_accuracy | cost_usd |" in text and "| a/one | 0.9 | 0.1 |" in text
    assert "No candidate" in markdown("draft", "dev", [])


def test_a_drafter_is_judged_by_another_family() -> None:
    assert judge_for("deepseek/deepseek-v4-flash", "qwen/qwen3.7-plus") == "qwen/qwen3.7-plus"
    assert judge_for("qwen/qwen3.5-flash-02-23", "qwen/qwen3.7-plus") == "moonshotai/kimi-k2.5"
    assert judge_for("moonshotai/kimi-k2.5", "moonshotai/kimi-k2.5") is None  # no judge of another family


def test_the_reference_gets_a_row_from_each_judge() -> None:
    # A Qwen drafter is judged by Kimi, so the reference needs a Kimi-judged row to be compared with.
    assert judges_for(REFERENCE, "qwen/qwen3.7-plus") == ["qwen/qwen3.7-plus", "moonshotai/kimi-k2.5"]
    assert judges_for(REFERENCE, "moonshotai/kimi-k2.5") == ["moonshotai/kimi-k2.5"]
    assert judges_for("deepseek/deepseek-v4-flash", "qwen/qwen3.7-plus") == ["qwen/qwen3.7-plus"]
    assert judges_for("moonshotai/kimi-k2.5", "moonshotai/kimi-k2.5") == []


def test_the_bench_refuses_a_database_that_is_not_a_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://vart:vart@localhost:5434/vart")
    assert main(["--step", "stance", "--models", "a/one"]) == 2

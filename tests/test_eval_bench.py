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


# --- fix round 1: failures, credit errors and the spend cap (fakes only; the engine calls are stubbed) ---

from types import SimpleNamespace  # noqa: E402

from app.contracts import ItemInput  # noqa: E402
from app.llm.client import LLMError  # noqa: E402
from evals import bench  # noqa: E402


class _Http(Exception):
    status_code = 402


class _Live:
    """Stands in for OpenRouterClient: each call costs `cost`; call number `credit_at` answers a 402."""

    cost = 1.0
    credit_at: int | None = None
    calls = 0

    def __init__(self, key: str) -> None:
        pass

    def complete(self, req: LLMRequest) -> LLMResult:
        type(self).calls += 1
        if type(self).calls == type(self).credit_at:
            err = LLMError("judge: APIStatusError")
            err.__cause__ = _Http()
            raise err
        return LLMResult("{}", 1, 1, type(self).cost, 1000)


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    class Live(_Live):
        calls = 0
        credit_at = None

    monkeypatch.setattr(bench, "OpenRouterClient", Live)
    monkeypatch.setattr(bench, "CANDIDATES", tmp_path)
    monkeypatch.setattr(
        bench,
        "ReplayClient",
        lambda path: SimpleNamespace(complete=lambda req: LLMResult("{}", 1, 1, 0.0, 1)),
    )
    monkeypatch.setattr(
        bench,
        "get_settings",
        lambda: SimpleNamespace(models=lambda: {"stance": "s/m", "judge": "qwen/qwen3.7-plus"}),
    )
    monkeypatch.setattr(
        bench, "decide", lambda passages, stances, dropped=(): SimpleNamespace(label="verified", value="Yes")
    )

    def fake_stance(llm, item, passages, model):  # type: ignore[no-untyped-def]
        llm.complete(build_request("stance", model, "p", "s", item.key, JudgeOut))
        return ()

    def fake_draft(llm, item, decision, model, spend, documents):  # type: ignore[no-untyped-def]
        llm.complete(build_request("draft", model, "p", "s", item.key, JudgeOut))
        return SimpleNamespace(text="t", source="model", problems=())

    def fake_judge(llm, item, decision, answer, model):  # type: ignore[no-untyped-def]
        llm.complete(build_request("judge", model, "p", "s", item.key, JudgeOut))
        if item.key == "bad":
            raise LLMError("judge: unusable")
        return JudgeOut(faithful=True, unsupported=[])

    monkeypatch.setattr(bench, "stance", fake_stance)
    monkeypatch.setattr(bench, "write_draft", fake_draft)
    monkeypatch.setattr(bench, "judge", fake_judge)
    return Live


def _inputs(*keys: str):  # type: ignore[no-untyped-def]
    items = [ItemInput(k, f"q {k}", None) for k in keys]
    pack = SimpleNamespace(
        name="dev",
        keys={
            k: SimpleNamespace(expected_label="verified", expected_value="Yes", honest_negative=False)
            for k in keys
        },
    )
    found = {k: SimpleNamespace(passages=[object()], dropped=()) for k in keys}
    return pack, items, found


def test_a_judge_error_counts_as_a_failure_and_the_rest_is_kept(rig) -> None:  # type: ignore[no-untyped-def]
    pack, items, found = _inputs("ok", "bad")
    rows = bench.bench_draft(pack, items, found, ["deepseek/x"], "k", 1, [], bench.Guard())
    assert rows[0]["failures"] == 1 and rows[0]["judge_faithfulness"] == 0.5


def test_draft_cost_includes_the_judge_calls(rig) -> None:  # type: ignore[no-untyped-def]
    pack, items, found = _inputs("a", "b")
    rows = bench.bench_draft(pack, items, found, ["deepseek/x"], "k", 1, [], bench.Guard())
    assert rows[0]["cost_usd"] == 4.0  # 2 drafts + 2 judge calls at 1.0


def test_a_credit_error_stops_the_run_with_a_partial_table(rig) -> None:  # type: ignore[no-untyped-def]
    rig.credit_at = 2  # the second model's call
    pack, items, found = _inputs("a")
    guard = bench.Guard()
    rows = bench.bench_stance(pack, items, found, ["m/one", "m/two", "m/three"], "k", 1, guard)
    assert [r["model"] for r in rows] == ["m/one"]
    assert guard.reason and "credit" in guard.reason
    assert "PARTIAL" in markdown("stance", "dev", rows, guard.reason)


def test_the_spend_cap_stops_the_run(rig) -> None:  # type: ignore[no-untyped-def]
    pack, items, found = _inputs("a", "b", "c", "d")
    guard = bench.Guard(2.5)
    rows = bench.bench_stance(pack, items, found, ["m/one"], "k", 1, guard)
    assert rows == [] and guard.reason and "cap" in guard.reason
    assert rig.calls == 3  # no call after the cap was reached

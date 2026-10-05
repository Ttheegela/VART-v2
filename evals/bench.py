r"""Model bench (spec 8): compares candidate models for one step on accuracy, cost and latency over the dev
pack and writes evals/results/bench-<step>.md. Live calls need OPENROUTER_API_KEY: the eval key (CLAUDE.md).

    python -m evals.bench --step stance --models \
        deepseek/deepseek-v4-flash,deepseek/deepseek-v4-pro,qwen/qwen3.5-flash-02-23,qwen/qwen3.7-plus,\
        z-ai/glm-5.3-flash,moonshotai/kimi-k2.5,openai/gpt-oss-120b,anthropic/claude-sonnet-5.5

The same list serves --step draft; the candidates are the model pool plus the quality reference
anthropic/claude-sonnet-5.5 (never a default).

Each candidate's calls are recorded under evals/recorded/candidates/ (git-ignored), so a rerun after a
network failure pays only for what is missing. The draft bench reads the stance decisions from the main
recording (evals/recorded/<pack>.jsonl), so record the main eval first."""

import argparse
import statistics
import sys
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.contracts import Decision, ItemInput, Retrieval
from app.db.models import Workspace
from app.db.session import database_url, get_engine
from app.decide import decide
from app.draft import write_draft
from app.llm.client import OPENROUTER_BASE_URL, LLMClient, LLMError, LLMRequest, LLMResult, OpenRouterClient
from app.llm.recorder import RecordingClient, ReplayClient, ReplayMiss
from app.retrieve import retrieve
from app.settings import get_settings
from app.stance import stance
from evals import pack as packs
from evals.judge import family, judge
from evals.run import RECORDED, RESULTS, always

CANDIDATES = RECORDED / "candidates"
JUDGE_FALLBACK = "moonshotai/kimi-k2.5"  # judges a candidate drafter from the default judge's family
REFERENCE = "anthropic/claude-sonnet-5.5"  # the quality reference (spec 8), never a default
MAX_BENCH_USD = 4.0  # live spend at which a run stops; the eval key's own cap is $5
OUT_OF_CREDIT = 402  # the HTTP status OpenRouter answers when a key's credit limit is used up


class BenchStop(Exception):
    """The run must stop (spend cap or out of credit); what finished is still written, marked partial."""


class Guard:
    """Live spend of the whole run (recorded replays cost nothing) and why the run stopped, if it did."""

    def __init__(self, max_usd: float = MAX_BENCH_USD) -> None:
        self.max_usd = max_usd
        self.total = 0.0
        self.reason: str | None = None
        self._lock = threading.Lock()

    def stop(self, reason: str) -> None:
        with self._lock:
            self.reason = self.reason or reason

    def add(self, usd: float) -> None:
        with self._lock:
            self.total += usd
            if self.total >= self.max_usd and not self.reason:
                self.reason = f"spend cap ${self.max_usd:.2f} reached"


class Guarded:
    """Sits on the live client only: counts what is really spent and stops the run at the cap or at a 402."""

    def __init__(self, inner: LLMClient, guard: Guard) -> None:
        self.inner = inner
        self.guard = guard

    def complete(self, req: LLMRequest) -> LLMResult:
        if self.guard.reason:
            raise BenchStop(self.guard.reason)
        try:
            result = self.inner.complete(req)
        except LLMError as exc:
            if getattr(exc.__cause__, "status_code", None) == OUT_OF_CREDIT:
                self.guard.stop("out of credit (the key's limit)")
                raise BenchStop(self.guard.reason) from exc
            raise
        self.guard.add(result.cost_usd or 0.0)
        return result


class Usage:
    """Thread-safe cost and latency of every call that went through it."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.calls: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def complete(self, req: LLMRequest) -> LLMResult:
        result = self.inner.complete(req)
        with self._lock:
            self.calls.append((result.cost_usd or 0.0, result.latency_ms or 0))
        return result


def catalog() -> dict[str, list[str]]:
    """OpenRouter's public model list: id -> supported parameters (no key needed)."""
    body = httpx.get(f"{OPENROUTER_BASE_URL}/models", timeout=30).json()
    return {m["id"]: m.get("supported_parameters", []) for m in body.get("data", [])}


def usable(models: Sequence[str], known: dict[str, list[str]]) -> list[str]:
    out = []
    for m in models:
        if m not in known:
            print(f"skip {m}: not in OpenRouter's catalog")
        elif "structured_outputs" not in known[m] and "response_format" not in known[m]:
            print(f"skip {m}: no structured outputs")
        else:
            out.append(m)
    return out


def judge_for(model: str, default: str) -> str | None:
    """The judge for a candidate drafter, always from another family (spec 6.14): the default judge, or
    JUDGE_FALLBACK when the candidate shares the default's family (a Qwen drafter is judged by Kimi)."""
    for judge_model in (default, JUDGE_FALLBACK):
        if family(model) != family(judge_model):
            return judge_model
    return None


def judges_for(model: str, default: str) -> list[str]:
    """Every judge a candidate's drafts get: judge_for's pick, plus JUDGE_FALLBACK for the reference, so that
    a candidate only the fallback can judge (a Qwen drafter) is compared with the reference under its own
    judge."""
    first = judge_for(model, default)
    if first is None:
        return []
    if model == REFERENCE and first != JUDGE_FALLBACK and family(JUDGE_FALLBACK) != family(model):
        return [first, JUDGE_FALLBACK]
    return [first]


def _parallel(fn: Callable[[ItemInput], Any], items: Sequence[ItemInput], workers: int) -> dict[str, Any]:
    with ThreadPoolExecutor(workers) as pool:
        return dict(zip((i.key for i in items), pool.map(fn, items), strict=True))


def _row(model: str, scores: dict[str, float], usages: Sequence[Usage], failures: int) -> dict[str, Any]:
    calls = [c for u in usages for c in u.calls]
    latencies = [ms for _, ms in calls] or [0]
    return {
        "model": model,
        **scores,
        "failures": failures,
        "cost_usd": round(sum(c for c, _ in calls), 4),
        "p50_seconds": round(statistics.median(latencies) / 1000, 2),
    }


def bench_stance(
    pack: packs.Pack,
    items: list[ItemInput],
    found: dict[str, Retrieval],
    models: list[str],
    key: str,
    workers: int,
    guard: Guard,
) -> list[dict[str, Any]]:
    rows = []
    for model in models:
        usage = Usage(
            RecordingClient(
                Guarded(OpenRouterClient(key), guard), CANDIDATES / f"stance-{model.replace('/', '_')}.jsonl"
            )
        )

        def one(item: ItemInput, model: str = model, usage: Usage = usage) -> Decision | None:
            passages = found[item.key].passages
            try:
                stances = stance(usage, item, passages, model) if passages else ()
            except LLMError:
                return None
            return decide(passages, stances, found[item.key].dropped)

        try:
            decisions = _parallel(one, items, workers)
        except BenchStop:
            break  # this model's row would be incomplete
        good = {c: d for c, d in decisions.items() if d is not None}
        keys = pack.keys
        scores = {
            "items": len(items),
            "label_accuracy": round(
                sum(
                    (d.label, d.value) == (keys[c].expected_label, keys[c].expected_value)
                    for c, d in good.items()
                )
                / len(items),
                4,
            ),
            "conflicts_caught": sum(
                d.label == "conflict" for c, d in good.items() if keys[c].expected_label == "conflict"
            ),
            "honest_negatives_kept": sum(
                (d.label, d.value) == ("verified", "No") for c, d in good.items() if keys[c].honest_negative
            ),
        }
        rows.append(_row(model, scores, [usage], len(items) - len(good)))
    return rows


def bench_draft(
    pack: packs.Pack,
    items: list[ItemInput],
    found: dict[str, Retrieval],
    models: list[str],
    key: str,
    workers: int,
    documents: list[str],
    guard: Guard,
) -> list[dict[str, Any]]:
    defaults = get_settings().models()
    main = ReplayClient(RECORDED / f"{pack.name}.jsonl")
    decisions = {
        i.key: decide(found[i.key].passages, stance(main, i, found[i.key].passages, defaults["stance"]))
        for i in items
        if found[i.key].passages
    }
    judged_items = [i for i in items if i.key in decisions and decisions[i.key].label != "unknown"]
    judge_client = RecordingClient(Guarded(OpenRouterClient(key), guard), CANDIDATES / "judge.jsonl")
    rows = []
    for model in models:
        judges = judges_for(model, defaults["judge"])
        if not judges:
            print(f"skip {model}: no judge from another family")
            continue
        usage = Usage(
            RecordingClient(
                Guarded(OpenRouterClient(key), guard), CANDIDATES / f"draft-{model.replace('/', '_')}.jsonl"
            )
        )
        judge_usage = Usage(judge_client)  # the judge calls of this model's drafts count in its cost

        def one(
            item: ItemInput,
            model: str = model,
            usage: Usage = usage,
            judges: list[str] = judges,
            judge_usage: Usage = judge_usage,
        ) -> tuple[str, bool, list[bool]] | None:
            try:
                draft = write_draft(usage, item, decisions[item.key], model, always, documents)
                verdicts = [
                    judge(judge_usage, item, decisions[item.key], draft.text, j).faithful for j in judges
                ]
            except LLMError:
                return None  # counted as a failure, and as unfaithful
            return draft.source, not draft.problems and draft.source == "model", verdicts

        try:
            results = _parallel(one, judged_items, workers)
        except BenchStop:
            break  # this model's rows would be incomplete
        out = {k: v for k, v in results.items() if v is not None}
        failures = len(results) - len(out)
        n = len(judged_items) or 1
        for k, judge_model in enumerate(judges):  # the reference gets one row per judge
            scores = {
                "items": len(judged_items),
                "first_drafts_pass": round(sum(first for _, first, _ in out.values()) / n, 4),
                "fallbacks": sum(src == "template" for src, _, _ in out.values()),
                "judge_faithfulness": round(sum(v[k] for _, _, v in out.values()) / n, 4),
            }
            rows.append({**_row(model, scores, [usage, judge_usage], failures), "judge": judge_model})
    return rows


def markdown(step: str, pack: str, rows: list[dict[str, Any]], partial: str | None = None) -> str:
    note = [f"PARTIAL: the run stopped early ({partial}); models after the last row were not benched.", ""]
    if not rows:
        return f"# Model bench: {step}\n\nNo candidate could be run.\n" + ("\n".join(note) if partial else "")
    columns = list(rows[0])
    lines = [
        f"# Model bench: {step} ({pack} pack, {date.today().isoformat()})",
        "",
        "Live calls from `python -m evals.bench`, not reproduced in CI; app/settings.py defaults follow it.",
        "",
        *(note if partial else []),
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    lines += ["| " + " | ".join(str(r[c]) for c in columns) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare candidate models for one step.")
    parser.add_argument("--step", choices=("stance", "draft"), required=True)
    parser.add_argument("--models", required=True, help="comma-separated OpenRouter model ids")
    parser.add_argument("--pack", default="dev")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--max-usd", type=float, default=MAX_BENCH_USD, help="stop when live spend reaches this"
    )
    args = parser.parse_args(argv)
    if "test" not in (make_url(database_url()).database or ""):  # the bench writes a workspace there
        print("refusing to run: DATABASE_URL must point at a test database", file=sys.stderr)
        return 2
    key = get_settings().openrouter_api_key
    if not key:
        print("OPENROUTER_API_KEY is not set (use the eval key, see CLAUDE.md)", file=sys.stderr)
        return 2
    models = usable([m.strip() for m in args.models.split(",") if m.strip()], catalog())
    pack = packs.load(args.pack)
    with Session(get_engine()) as session:
        ws = Workspace()
        session.add(ws)
        session.commit()
        try:
            packs.load_documents(
                session,
                ws.id,
                pack,
                list(pack.facts.documents),
                source="sample",
                llm=None,
                model="",
                spend=always,
            )
            items = [i for q in packs.QUESTIONNAIRES for i in pack.items(q)]
            found = {i.key: retrieve(session, ws.id, i.question, i.topic) for i in items}
            session.commit()
        finally:
            session.execute(delete(Workspace).where(Workspace.id == ws.id))
            session.commit()
    documents = [d.filename for d in pack.facts.documents]
    guard = Guard(args.max_usd)
    try:
        if args.step == "stance":
            rows = bench_stance(pack, items, found, models, key, args.workers, guard)
        else:
            rows = bench_draft(pack, items, found, models, key, args.workers, documents, guard)
    except ReplayMiss as exc:
        print(
            f"the draft bench reads the main recording; record the main eval first ({exc})", file=sys.stderr
        )
        return 2
    out = RESULTS / f"bench-{args.step}.md"
    out.write_text(markdown(args.step, args.pack, rows, guard.reason))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

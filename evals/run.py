"""Run the whole engine over a company pack and score it against the keys (spec 8).

    python -m evals.run --pack dev                  # replay recordings: no network, what CI runs
    python -m evals.run --pack dev --mode record    # needs OPENROUTER_API_KEY: the eval key, see CLAUDE.md
    python -m evals.run --pack gap-dev              # the CSF gap check (evals/gap.py)

Writes evals/results/latest.{json,md} (gap-dev: evals/results/gap-dev.{json,md}); exits 0 when every gate
passes, 1 when one fails, 2 when a recording
is missing, a record run left a request unrecorded, or the setup is wrong. Replay never calls a model; a
missing recording stops the run (Plan 1A Task 4: ReplayMiss is caught before any other LLMError)."""

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, get_args

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.classify import PROMPT_VERSION as CLASSIFY_PROMPT
from app.contracts import ItemInput, ItemResult, OpenItem, jsonable
from app.db.models import Document, DocumentLine, Workspace
from app.db.session import database_url, get_engine
from app.draft import PROMPT_VERSION as DRAFT_PROMPT
from app.draft import check
from app.ingest.store import store_statement
from app.interview import plan_queue, recheck
from app.llm.client import LLMClient, LLMError, LLMRequest, LLMResult, OpenRouterClient
from app.llm.recorder import RecordingClient, ReplayClient, ReplayMiss
from app.observability import Step
from app.pipeline import answer_item
from app.settings import get_settings
from app.stance import PROMPT_VERSION as STANCE_PROMPT
from datakit.extract import lines_of, text_of
from evals import pack as packs
from evals import score
from evals.judge import PROMPT_VERSION as JUDGE_PROMPT
from evals.judge import family, judge

ROOT = Path(__file__).resolve().parent.parent
RECORDED = ROOT / "evals" / "recorded"
RESULTS = ROOT / "evals" / "results"
ANSWERS = ROOT / "evals" / "fixtures"
STATEMENT_DATE = date(2026, 10, 4)  # fixed so statement prompts and recordings never change with the clock


def always(step: str) -> bool:
    """Evals measure the engine, not the budget (Plan 3 tests budgets end to end)."""
    return True


class Log:
    """Remembers every request: record mode keeps only the recordings a run used; the redaction stage scans
    what was sent for private strings."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResult:
        self.requests.append(req)
        return self.inner.complete(req)


def client(mode: str, path: Path) -> LLMClient:
    if mode == "replay":
        return ReplayClient(path)
    key = get_settings().openrouter_api_key
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set (use the eval key, see CLAUDE.md)")
    live = OpenRouterClient(key)
    return live if mode == "live" else RecordingClient(live, path)


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="surrogatepass")
    return [json.loads(x) for x in text.split("\n") if x.strip()]


def keep_used(path: Path, keys: set[str]) -> None:
    """After a record run: drop recordings no request used, sort the rest by key (stable diffs)."""
    kept = sorted((r for r in _rows(path) if r["key"] in keys), key=lambda r: r["key"])
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in kept)
    path.write_text(text, encoding="utf-8", errors="surrogatepass")


def drop_steps(path: Path, steps: set[str]) -> None:
    """Record mode with --refresh: forget the recorded rows of these steps, so they are requested again (a row
    whose text failed validation would otherwise be replayed for ever)."""
    if not path.exists():
        return
    rows = [
        x
        for x in path.read_text(encoding="utf-8", errors="surrogatepass").split("\n")
        if x.strip() and json.loads(x)["step"] not in steps
    ]
    path.write_text("".join(x + "\n" for x in rows), encoding="utf-8", errors="surrogatepass")


def _stored(session: Session, workspace_id: uuid.UUID) -> dict[str, list[str]]:
    rows = session.execute(
        select(DocumentLine.document_id, DocumentLine.text)
        .join(Document, Document.id == DocumentLine.document_id)
        .where(Document.workspace_id == workspace_id)
        .order_by(DocumentLine.document_id, DocumentLine.n)
    )
    out: dict[str, list[str]] = {}
    for doc_id, text in rows:
        out.setdefault(str(doc_id), []).append(text)
    return out


def _metadata(session: Session, doc_ids: dict[str, str]) -> dict[str, tuple[Any, ...]]:
    """Fact-sheet document id -> (kind, status, effective_date, scope, evidence_allowed), as stored."""
    out = {}
    for fact_id, doc_id in doc_ids.items():
        d = session.get_one(Document, uuid.UUID(doc_id))
        out[fact_id] = (d.kind, d.status, d.effective_date, d.scope, d.evidence_allowed)
    return out


def _answer_all(
    session: Session,
    workspace_id: uuid.UUID,
    items: Sequence[ItemInput],
    llm: LLMClient,
    models: dict[str, str],
) -> dict[str, ItemResult]:
    return {i.key: answer_item(session, workspace_id, i, llm, models, always) for i in items}


def _interview(
    session: Session,
    workspace_id: uuid.UUID,
    pack: packs.Pack,
    results: dict[str, ItemResult],
    llm: LLMClient,
    models: dict[str, str],
) -> tuple[list[str], int, dict[str, list[Any]], list[str]]:
    """The queue, how often any item came back after being asked, the fills a scripted answer suggests, and
    the ids of the stored statement documents."""
    scripted: dict[str, str] = json.loads((ANSWERS / f"{pack.name}-answers.json").read_text(encoding="utf-8"))
    queue: list[str] = []
    asked_twice = 0
    suggestions: dict[str, list[Any]] = {}
    statements: list[str] = []
    for q in packs.QUESTIONNAIRES:
        items = [
            OpenItem(i, results[i.key].decision.label, 0, results[i.key].draft.text) for i in pack.items(q)
        ]
        first = plan_queue(items)
        queue += [e.key for e in first]
        asked: dict[str, int] = {}
        current = list(items)
        for _ in range(3 * len(items)):  # a planner that re-queued forever must not hang the run
            entries = plan_queue(current)
            if not entries:
                break
            asked[entries[0].key] = asked.get(entries[0].key, 0) + 1
            current = [replace(o, asked=asked.get(o.item.key, 0)) for o in current]
        asked_twice += sum(n > 1 for n in asked.values())
        for code, answer in scripted.items():
            if code not in {i.key for i in pack.items(q)}:
                continue
            statement = store_statement(
                session, workspace_id, answer, filename=f"answer-{code}.txt", today=STATEMENT_DATE
            )
            statements.append(str(statement.id))
            topic = next(i.topic for i in pack.items(q) if i.key == code)
            open_items = [o for o in items if o.item.key != code]
            suggestions[code] = recheck(
                session, workspace_id, statement.id, topic, open_items, llm, models["recheck"], always
            )
    return queue, asked_twice, suggestions, statements


def _redaction(pack: packs.Pack, llm: LLMClient, models: dict[str, str]) -> score.RedactionObserved:
    """Plan 1A Ruling 10: the pack loaded as uploads (redacted), MVSP-B answered from it. The documents are
    the ones MVSP-B's key cites plus every one that names a person (17 of the dev pack's 22, under the
    20-document upload limit)."""
    private = pack.private_strings()
    cited = {e.doc for i in pack.items("mvsp-b") for e in pack.keys[i.key].evidence}
    specs = [
        d for d in pack.facts.documents if d.id in cited or any(s in text_of(pack.path(d)) for s in private)
    ]
    log = Log(llm)
    with Session(get_engine()) as session:
        ws = Workspace()
        session.add(ws)
        session.commit()
        try:
            doc_ids = packs.load_documents(
                session, ws.id, pack, specs, source="upload", llm=log, model=models["classify"], spend=always
            )
            results = _answer_all(session, ws.id, pack.items("mvsp-b"), log, models)
            stored = _stored(session, ws.id)
        finally:
            session.execute(delete(Workspace).where(Workspace.id == ws.id))
            session.commit()
    if not results:  # score() reads 0 of 0 as 1.0, so an empty stage would pass every redaction gate
        raise ValueError("the redaction stage answered no items: its gates would pass on nothing")
    sent = [r.user for r in log.requests]
    leaks = _leaks(private, [*sent, *(x for lines in stored.values() for x in lines)])
    return score.RedactionObserved(results, doc_ids, stored, leaks)


def _leaks(private: Sequence[str], texts: Sequence[str]) -> int:
    return sum(s in text for s in private for text in texts)


def run(pack_name: str, llm: LLMClient, models: dict[str, str]) -> dict[str, Any]:
    pack = packs.load(pack_name)
    log = Log(llm)  # the interview's requests are scanned for the visitor's private strings
    with Session(get_engine()) as session:
        ws = Workspace()
        session.add(ws)
        session.commit()
        try:
            specs = list(pack.facts.documents)
            doc_ids = packs.load_documents(
                session, ws.id, pack, specs, source="sample", llm=llm, model=models["classify"], spend=always
            )
            items = [i for q in packs.QUESTIONNAIRES for i in pack.items(q)]
            results = _answer_all(session, ws.id, items, llm, models)
            documents = [d.filename for d in specs]
            judged, checks = {}, {}
            for item in items:
                r = results[item.key]
                if r.draft.text:
                    # a template is not the drafter's work (write_draft swallows its failures): not judged, so
                    # it counts as unfaithful, the same rule as the draft bench
                    if r.draft.source == "model":
                        judged[item.key] = judge(
                            llm, item, r.decision, r.draft.text, models["judge"]
                        ).faithful
                    checks[item.key] = check(r.draft.text, r.decision, documents)
            queue, asked_twice, suggestions, statements = _interview(
                session, ws.id, pack, results, log, models
            )
            stored = _stored(session, ws.id)
            observed = score.Observed(
                results=results,
                doc_ids=doc_ids,
                stored=stored,
                metadata=_metadata(session, doc_ids),
                reference={d.id: lines_of(pack.path(d)) for d in specs},
                judged=judged,
                checks=checks,
                queue=queue,
                asked_twice=asked_twice,
                suggestions=suggestions,
            )
        finally:
            session.execute(delete(Workspace).where(Workspace.id == ws.id))
            session.commit()
    # sample documents legitimately name people; the visitor's statements and the rechecks about them must not
    interview_leaks = _leaks(
        pack.private_strings(),
        [
            *(x for sid in statements for x in stored.get(sid, [])),
            *(r.user for r in log.requests if r.step == "recheck"),
        ],
    )
    red = _redaction(pack, llm, models)
    observed.redaction = replace(red, leaks=red.leaks + interview_leaks)
    metrics = score.score(pack, observed)
    return {
        "pack": pack_name,
        "models": models,
        "prompts": [CLASSIFY_PROMPT, STANCE_PROMPT, DRAFT_PROMPT, JUDGE_PROMPT],
        "metrics": metrics,
        "gates": score.gates(metrics),
        "label_misses": score.label_misses(pack, observed),
        "items": {
            code: {
                "label": r.decision.label,
                "value": r.decision.value,
                "citations": len(r.decision.citations),
                "dropped": sorted(d.reason for d in r.decision.dropped),
                "draft": r.draft.source,
            }
            for code, r in sorted(results.items())
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--pack", default="dev")
    parser.add_argument("--mode", choices=("replay", "record", "live"), default="replay")
    parser.add_argument(
        "--refresh",
        default="",
        help="record mode: comma-separated steps whose recorded rows are requested again",
    )
    args = parser.parse_args(argv)
    refresh = {x.strip() for x in args.refresh.split(",") if x.strip()}
    if refresh and args.mode != "record":
        print("--refresh needs --mode record", file=sys.stderr)
        return 2
    if unknown := sorted(refresh - set(get_args(Step))):
        print(
            f"--refresh: unknown step {', '.join(unknown)} (steps: {', '.join(get_args(Step))})",
            file=sys.stderr,
        )
        return 2
    if "test" not in (make_url(database_url()).database or ""):
        print("refusing to run: DATABASE_URL must point at a test database", file=sys.stderr)
        return 2
    models = get_settings().models()
    if family(models["judge"]) == family(models["draft"]):
        print(
            "the judge must come from a different model family than the drafter (spec 6.14)", file=sys.stderr
        )
        return 2
    path = RECORDED / f"{args.pack}.jsonl"
    if refresh:
        drop_steps(path, refresh)
    log = Log(client(args.mode, path))
    try:
        if args.pack == "gap-dev":
            from evals import gap  # imported here: evals.gap imports this module

            report = gap.run(log, models)
        else:
            report = run(args.pack, log, models)
    except ReplayMiss as exc:
        print(f"recording missing ({exc}); re-record with --mode record", file=sys.stderr)
        return 2
    except LLMError as exc:  # exit 1 is the gate-failure code
        print(
            f"model call failed ({exc}); if a recorded reply is unusable, re-record that step with "
            "--mode record --refresh STEP",
            file=sys.stderr,
        )
        return 2
    if args.mode == "record":
        # a failed live call the engine swallowed (write_draft's template fallback) leaves no row: the run
        # passes, but its recording would not replay
        keys = {r.key() for r in log.requests}
        if unrecorded := keys - {r["key"] for r in _rows(path)}:
            n = len(unrecorded)
            print(
                f"{n} request{'s' if n > 1 else ''} went unrecorded (a live call failed and was swallowed); "
                "the recording would not replay: record again",
                file=sys.stderr,
            )
            return 2
        keep_used(path, keys)
    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = "gap-dev" if args.pack == "gap-dev" else "latest"  # each pack keeps its own committed results
    (RESULTS / f"{stem}.json").write_text(json.dumps(jsonable(report), indent=2, sort_keys=True) + "\n")
    (RESULTS / f"{stem}.md").write_text(score.markdown(report))
    failed = [name for name, g in report["gates"].items() if not g["pass"]]
    print(
        f"{len(report['gates']) - len(failed)}/{len(report['gates'])} gates pass"
        + (f"; failed: {', '.join(failed)}" if failed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

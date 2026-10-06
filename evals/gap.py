"""The CSF 2.0 gap-check eval (CSF spec 8), pack gap-dev: the dev company's 22 documents plus the gap
extension's (data/dev/gap), the workspace's built-in CSF questionnaire for the core, every Checked outcome
through answer_item, then the Ask-me outcomes answered from evals/fixtures/gap-dev-answers.json (one left
unanswered), scored against data/dev/key/csf-core.yaml. `python -m evals.run --pack gap-dev` lands here.

Every gate fails closed (None) when it has nothing to measure, like the questionnaire gates."""

import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import csf
from app.contracts import ItemResult
from app.db.models import Document, Item, Workspace
from app.db.session import get_engine
from app.draft import PROMPT_VERSION as DRAFT_PROMPT
from app.ingest.store import ingest_document, store_statement
from app.llm.client import LLMClient
from app.stance import PROMPT_VERSION as STANCE_PROMPT
from datakit import csf as csf_data
from datakit import gap as gap_data
from datakit.schemas import Facts, GapFacts, Key, KeyItem, load_yaml
from evals import pack as packs
from evals import score
from evals.run import Log, _leaks, _stored, always  # evals.run imports this module only inside main()

NAME = "gap-dev"
ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "evals" / "fixtures" / "gap-dev-answers.json"
# Fixed, so stored statements never change with the clock; separate from evals.run's on purpose, so the dev
# pack's recordings and this pack's never depend on each other.
STATEMENT_DATE = date(2026, 10, 5)
SECRETS = ("sk9Kestrel2026xQ",)  # the fake API key planted in the fixture's supply-chain answer
GATES: dict[str, tuple[str, float]] = {
    "cited_coverage": (">=", 1.0),
    "trap_coverage": ("<=", 0.0),
    "label_accuracy": (">=", 0.80),
    "disagreements_caught": (">=", 1.0),
    "stated_noncompliance": (">=", 1.0),
    "nist_text_intact": (">=", 1.0),
    "honest_tiers": (">=", 1.0),
    "redaction_private_leaks": ("<=", 0.0),
}


@dataclass(frozen=True)
class GapPack:
    dev: packs.Pack
    gap: GapFacts
    facts: Facts  # the dev fact sheet merged with the gap extension
    control: dict[str, str]  # Checked CSF id -> fact-sheet control
    keys: dict[str, KeyItem]  # Checked CSF id -> key entry
    nist: dict[str, dict[str, Any]]  # CSF id -> NIST's fields, from the committed extract of NIST's export
    tiers: dict[str, str]  # CSF id -> tier (data/csf/tiers.yaml through the built file)


@dataclass
class GapObserved:
    results: dict[str, ItemResult]  # Checked CSF id -> what the engine produced
    labels: dict[str, str | None]  # every CSF id -> the gap label shown (None: no label)
    items: list[str]  # CSF ids of the built-in questionnaire's items, as stored, in order
    statements: dict[str, str]  # answered Ask-me CSF id -> stored statement documents.id
    kinds: dict[str, str]  # statement documents.id -> kind as stored
    doc_ids: dict[str, str]  # fact-sheet document id -> documents.id
    stored: dict[str, list[str]]  # documents.id -> stored lines
    leaks: int  # private strings found in stored statements or in model requests
    private: int  # private strings planted in the Ask-me answers
    nist: dict[str, dict[str, Any]]  # CSF id -> NIST's fields as the app loaded and showed them


def load() -> GapPack:
    facts, gap = gap_data.load("dev")
    key = load_yaml(ROOT / "data" / "dev" / "key" / f"{gap_data.NAME}.yaml", Key)
    return GapPack(
        packs.load("dev"),
        gap,
        gap_data.merged(facts, gap),
        {m.csf_id: m.control for m in gap.outcomes},
        {k.code: k for k in key.items},
        {o["id"]: o for o in csf_data.load()[0]["outcomes"]},
        {o.id: o.tier for o in csf.framework().outcomes},
    )


def shown(o: csf.Outcome) -> dict[str, Any]:
    """NIST's fields of an outcome as the app holds it, in the extract's form."""
    return {
        "id": o.id,
        "function": o.function,
        "category": o.category,
        "outcome": o.outcome,
        "related_controls": list(o.related_controls),
    }


def run(llm: LLMClient, models: dict[str, str]) -> dict[str, Any]:
    pack = load()
    fw = csf.framework()
    answers: dict[str, str] = json.loads(ANSWERS.read_text(encoding="utf-8"))
    log = Log(llm)
    with Session(get_engine()) as session:
        ws = Workspace()
        session.add(ws)
        session.commit()
        try:
            doc_ids: dict[str, str] = {}
            for spec in pack.facts.documents:  # the dev sheet's order, then the extension's
                doc = ingest_document(
                    session,
                    ws.id,
                    spec.filename,
                    gap_data.doc_path("dev", pack.gap, spec).read_bytes(),
                    source="sample",
                    llm=log,
                    model=models["classify"],
                    spend=always,
                )
                doc_ids[spec.id] = str(doc.id)
            q = csf.questionnaire_for(session, ws.id, "core")
            items = [
                x
                for x in session.scalars(
                    select(Item.csf_id).where(Item.questionnaire_id == q.id).order_by(Item.position)
                )
                if x is not None
            ]
            session.commit()
            outcomes = [fw.get(x) for x in items]
            results: dict[str, ItemResult] = {}
            for o in outcomes:
                result = csf.check_outcome(session, ws.id, o, log, models, always)
                if result is not None:
                    results[o.id] = result
            # Ruling 1: the Ask-me answers are stored only after every Checked outcome is answered, so none is
            # retrievable evidence for a Checked outcome (spec 5.4: an answer re-checks outcomes later)
            statements: dict[str, str] = {}
            for o in outcomes:
                if o.id not in results and o.id in answers:
                    doc = store_statement(
                        session, ws.id, answers[o.id], filename=f"answer-{o.id}.txt", today=STATEMENT_DATE
                    )
                    statements[o.id] = str(doc.id)
            stored = _stored(session, ws.id)
            kinds = {sid: session.get_one(Document, uuid.UUID(sid)).kind for sid in statements.values()}
        finally:
            session.execute(delete(Workspace).where(Workspace.id == ws.id))
            session.commit()
    labels: dict[str, str | None] = {}
    for o in fw.outcomes:
        r = results.get(o.id)
        if r is not None:
            labels[o.id] = csf.gap_label(o, r.decision.label, r.decision.value)
        elif o.id in statements:
            labels[o.id] = csf.gap_label(o, "user_confirmed", None, statements[o.id])
        else:
            labels[o.id] = csf.gap_label(o, None)
    # sample documents name people legitimately; the visitor's answers must reach neither storage nor a model
    private = [s for s in (*pack.dev.private_strings(), *SECRETS) if any(s in a for a in answers.values())]
    leaks = _leaks(private, [x for sid in statements.values() for x in stored.get(sid, [])])
    leaks += _leaks(SECRETS, [r.user for r in log.requests])
    nist = {o.id: shown(o) for o in fw.outcomes}
    obs = GapObserved(results, labels, items, statements, kinds, doc_ids, stored, leaks, len(private), nist)
    metrics = score_gap(pack, obs)
    steps = {"stance", "draft"} | {r.step for r in log.requests}  # an unexpected step (classify) shows here
    return {
        "pack": NAME,
        "models": {k: models[k] for k in sorted(steps)},
        "prompts": [STANCE_PROMPT, DRAFT_PROMPT],
        "metrics": metrics,
        "gates": score.gates(metrics, GATES),
        "label_misses": misses(pack, obs),
        "items": {
            code: {
                "label": labels[code],
                "decide": r.decision.label,
                "value": r.decision.value,
                "citations": len(r.decision.citations),
                "dropped": sorted(d.reason for d in r.decision.dropped),
                "draft": r.draft.source,
            }
            for code, r in sorted(results.items())
        },
    }


def trap_outcomes(pack: GapPack) -> list[str]:
    """Checked outcomes every statement about whose control is in a template, a draft or only planned
    (spec 8). Trap G4 (planned-only on DE.AE-06) is not one: a final policy also speaks to that control, so
    DE.AE-06 is a planted disagreement; the planned-only kind is measured on ID.RA-02 and DE.AE-07."""
    return [c for c in pack.keys if gap_data.trap_sources(pack.facts, pack.control[c])]


def _expected(pack: GapPack) -> dict[str, str | None]:
    fw = csf.framework()
    return {c: csf.gap_label(fw.get(c), k.expected_label, k.expected_value) for c, k in pack.keys.items()}


def _got(pack: GapPack, obs: GapObserved) -> dict[str, str | None]:
    fw = csf.framework()
    return {
        c: csf.gap_label(fw.get(c), obs.results[c].decision.label, obs.results[c].decision.value)
        for c in pack.keys
    }


def score_gap(pack: GapPack, obs: GapObserved) -> dict[str, float | None]:
    if missing := sorted(set(pack.keys) - set(obs.results)):  # a key with no result must fail loudly
        raise ValueError(f"no result for Checked outcomes: {', '.join(missing)}")
    m: dict[str, float | None] = {}
    want, got = _expected(pack), _got(pack, obs)
    shown_codes = [c for c in pack.keys if got[c] in ("covered", "partly_covered")]
    m["cited_coverage"] = score._gated(
        *score._citation_counts([obs.results[c].decision for c in shown_codes], obs.stored)
    )

    # Trap coverage, counted per trap outcome. Judged by the fact sheet's truth, not the classifier's
    # (decide drops what the classifier marked not evidence and caps an all-draft answer, so a misclassified
    # template or draft gets past it): a shown citation of a template or of a document outside the fact sheet
    # (an Ask-me statement, Ruling 1), and a Covered answer resting only on drafts, count too.
    specs = {obs.doc_ids[d.id]: d for d in pack.facts.documents if d.id in obs.doc_ids}
    traps = trap_outcomes(pack)
    bad = 0
    for c in shown_codes:
        cited = [specs.get(x.document_id) for x in obs.results[c].decision.citations]
        bad += sum(s is None or not s.evidence_allowed for s in cited)
        drafts_only = bool(cited) and all(s is not None and s.status == "draft" for s in cited)
        bad += got[c] == "covered" and (c in traps or drafts_only)
    m["trap_coverage"] = score._count(bad, len(traps))

    m["label_accuracy"] = score._gated(sum(got[c] == want[c] for c in pack.keys), len(pack.keys))
    for name, label in (("disagreements_caught", "documents_disagree"), ("stated_noncompliance", "not_met")):
        planted = [c for c in pack.keys if want[c] == label]
        m[name] = score._gated(sum(got[c] == label for c in planted), len(planted))

    # NIST text intact: every outcome the run showed has NIST's fields from the committed extract, and the
    # drift check (CSF spec 4) passes
    ids = set(pack.nist) | set(obs.nist)
    same = sum(i in pack.nist and obs.nist.get(i) == pack.nist[i] for i in ids)
    m["nist_text_intact"] = (0.0 if csf_data.check() else score._gated(same, len(ids))) if pack.nist else None

    # Honest tiers: a not-checked outcome is no item, no result and no label; an Ask-me outcome is never sent
    # through the engine and shows Confirmed by you only with a stored statement that holds lines
    honest = cases = 0
    for oid, tier in pack.tiers.items():
        if tier == "not_checked":
            cases += 1
            honest += oid not in obs.items and oid not in obs.results and obs.labels.get(oid) is None
        elif tier == "ask":
            cases += 1
            sid = obs.statements.get(oid)
            backed = sid is None or (obs.kinds.get(sid) == "statement" and bool(obs.stored.get(sid)))
            shows = "confirmed_by_you" if sid is not None else "not_answered"
            honest += obs.labels.get(oid) == shows and oid not in obs.results and backed
    m["honest_tiers"] = score._gated(honest, cases)
    m["redaction_private_leaks"] = score._count(obs.leaks, obs.private)

    recalls = [
        sum(score._found(obs.results[c], obs.doc_ids[e.doc], e.quote) is not None for e in k.evidence)
        / len(k.evidence)
        for c, k in pack.keys.items()
        if k.evidence
    ]
    m["retrieval_recall_at_8"] = round(statistics.fmean(recalls), 4) if recalls else None
    m["cost_usd_per_core_run"] = round(sum(r.cost_usd for r in obs.results.values()), 4)
    m["seconds_per_core_run"] = round(sum(r.latency_ms for r in obs.results.values()) / 1000, 2)
    return m


def misses(pack: GapPack, obs: GapObserved) -> list[str]:
    want, got = _expected(pack), _got(pack, obs)
    return [f"{c}: expected {want[c]}, got {got[c]}" for c in sorted(pack.keys) if want[c] != got[c]]

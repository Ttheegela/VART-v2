"""NIST CSF 2.0 gap check (CSF spec 4-6): the bundled outcomes, scopes, and the gap labels, a display
mapping over decide's output per part, combined by code (decide itself does not change).
data/csf/csf-2.0.json is built and drift-tested by datakit/csf.py; the app only reads it."""

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Literal, get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import (
    Citation,
    Conflict,
    ConflictSide,
    Decision,
    Draft,
    Dropped,
    ItemInput,
    ItemLabel,
    ItemResult,
    Label,
    OpenItem,
    QueueEntry,
    Retrieval,
    Spend,
    Stance,
    Value,
)
from app.db.models import Item, Questionnaire, Workspace
from app.decide import CONFIDENCE, QUOTE_FAILURES
from app.draft import template_answer
from app.interview import plan_queue
from app.llm.client import LLMClient
from app.pipeline import answer_retrieved
from app.retrieve import retrieve

DATA = Path(__file__).resolve().parent.parent / "data" / "csf" / "csf-2.0.json"
Tier = Literal["checked", "ask", "not_checked"]
Scope = Literal["core", "govern", "identify", "protect", "detect", "respond", "recover"]
SCOPES: tuple[str, ...] = get_args(Scope)
GapLabel = Literal[
    "covered", "partly_covered", "not_met", "documents_disagree", "gap", "confirmed_by_you", "not_answered"
]
PartLabel = Literal[
    "covered", "partly_covered", "not_met", "documents_disagree", "gap"
]  # a Checked part's label (M12)
GAP_WORDS: dict[str, str] = {
    "covered": "Covered",
    "partly_covered": "Partly covered",
    "not_met": "Not met (stated)",
    "documents_disagree": "Documents disagree",
    "gap": "Gap",
    "confirmed_by_you": "Confirmed by you",
    "not_answered": "Not answered",
}
NOT_CHECKED = "not checked in this version"
FUNCTIONS = ("Govern", "Identify", "Protect", "Detect", "Respond", "Recover")
_ID = re.compile(r"[A-Z]{2}\.[A-Z]{2}-\d{2}")
_CHECKED: dict[tuple[str, str | None], PartLabel] = {  # CSF spec 5.3
    ("verified", "Yes"): "covered",
    ("partial", "Partial"): "partly_covered",
    ("verified", "No"): "not_met",
    ("conflict", None): "documents_disagree",
    ("unknown", None): "gap",
}
_DECIDE: dict[
    PartLabel, tuple[Label, Value | None]
] = {  # the inverse of _CHECKED: a combined label as decide's
    "covered": ("verified", "Yes"),
    "partly_covered": ("partial", "Partial"),
    "not_met": ("verified", "No"),
    "documents_disagree": ("conflict", None),
    "gap": ("unknown", None),
}
PART_WORDS: dict[PartLabel, str] = {  # the explanation's groups, in this order
    "covered": "Evidenced",
    "partly_covered": "Partly evidenced",
    "not_met": "Stated as not done",
    "documents_disagree": "Documents disagree",
    "gap": "No evidence",
}
_DECIDING: dict[
    PartLabel, tuple[PartLabel, ...]
] = {  # whose quotes explain each combined label (spec 5.3, C2)
    "documents_disagree": ("documents_disagree",),
    "not_met": ("not_met",),
    "covered": ("covered",),
    "partly_covered": ("covered", "partly_covered"),
    "gap": (),
}


@dataclass(frozen=True)
class Outcome:
    id: str
    function: str
    category: str
    outcome: str  # NIST's text, verbatim
    related_controls: tuple[str, ...]
    source_url: str
    tier: Tier
    question: str | None  # VART's phrasing; None when not checked
    parts: tuple[str, ...] = ()  # VART's: NIST's text cut by spec 4's rule; checked only


@dataclass(frozen=True)
class Framework:
    version: str
    retrieved: str
    outcomes: tuple[Outcome, ...]

    def get(self, csf_id: str) -> Outcome:
        return {o.id: o for o in self.outcomes}[csf_id]


def outcome_or_none(csf_id: str) -> Outcome | None:
    """The deployed outcome with this id, or None for an id a data refresh withdrew (adversary-1 N1): only a
    run started before the deploy holds one, and it must not crash a step or a request."""
    return next((o for o in framework().outcomes if o.id == csf_id), None)


def _validate(outcomes: tuple[Outcome, ...]) -> None:
    """Fail loudly on a hand-edited data file: the cached loader is trusted all process long."""
    seen: set[str] = set()
    for o in outcomes:
        if not _ID.fullmatch(o.id):
            raise ValueError(f"{o.id!r}: not a CSF outcome id")
        if o.id in seen:
            raise ValueError(f"{o.id}: duplicate id")
        seen.add(o.id)
        if o.function not in FUNCTIONS:
            raise ValueError(f"{o.id}: unknown function {o.function!r}")
        if o.tier not in get_args(Tier):
            raise ValueError(f"{o.id}: unknown tier {o.tier!r}")
        if o.tier != "not_checked" and not (o.question and o.question.strip()):
            raise ValueError(f"{o.id}: a {o.tier} outcome needs a question")
        if o.tier == "checked" and not (o.parts and all(p.strip() for p in o.parts)):
            raise ValueError(f"{o.id}: a checked outcome needs parts")
        if o.tier != "checked" and o.parts:
            raise ValueError(f"{o.id}: only a checked outcome has parts")


@cache
def framework() -> Framework:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    outcomes = tuple(
        Outcome(
            o["id"],
            o["function"],
            o["category"],
            o["outcome"],
            tuple(o["related_controls"]),
            o["source_url"],
            o["tier"],
            o["question"],
            tuple(o["parts"]),
        )
        for o in raw["outcomes"]
    )
    _validate(outcomes)
    return Framework(raw["csf_version"], raw["retrieved"], outcomes)


def in_scope(scope: str) -> tuple[Outcome, ...]:
    """The Checked and Ask-me outcomes of the whole core or of one function (spec 5.1), in NIST's order."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}: one of {', '.join(SCOPES)}")
    return tuple(
        o for o in framework().outcomes if o.tier != "not_checked" and scope in ("core", o.function.lower())
    )


def item_input(o: Outcome) -> ItemInput:
    if o.question is None:
        raise ValueError(f"{o.id} has no question: it is {NOT_CHECKED}")
    return ItemInput(o.id, o.question, o.category)


def gap_label(
    o: Outcome, label: ItemLabel | None, value: Value | None = None, statement_id: object | None = None
) -> GapLabel | None:
    """No label for a not-checked outcome (spec 5.5). Confirmed by you needs a stored statement (spec 5.4);
    an Ask-me outcome without one is Not answered. A Checked outcome maps decide's label and value (spec 5.3);
    `na` and an outcome not run yet have no label."""
    if o.tier == "not_checked":
        return None
    if label == "user_confirmed" and statement_id is not None:
        return "confirmed_by_you"
    if o.tier == "ask":
        return "not_answered"
    return _CHECKED.get((label or "", value))


FILENAME = "csf-2.0"


def _digest(outcomes: Sequence[Outcome]) -> str:
    rows = [[o.id, o.tier, o.question, o.category, list(o.parts)] for o in outcomes]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def current_mapping(scope: str) -> dict[str, str]:
    """What names the built-in questionnaire for `scope` under the CSF data deployed now (CSF spec 6): the
    data version, its retrieval date, the scope and a digest of its items. ValueError for an unknown scope."""
    outcomes = in_scope(scope)
    fw = framework()
    return {"csf_version": fw.version, "retrieved": fw.retrieved, "scope": scope, "digest": _digest(outcomes)}


def questionnaire_for(session: Session, workspace_id: uuid.UUID, scope: str) -> Questionnaire:
    """The workspace's built-in CSF questionnaire for `scope` (CSF spec 6), created on first use with one
    item per Checked and Ask-me outcome in scope. It is reused only while the CSF data behind it is the same
    (version, retrieval date, scope and a digest of the items), so a deploy that changes the tiers or a
    question gives the next run new items instead of stale ones. Found by those mapping keys (JSONB
    containment), so a key added to the mapping later does not hide it. Commits."""
    outcomes = in_scope(scope)
    mapping = current_mapping(scope)
    # Lock the workspace row, as ingest does, so two first calls at once create one questionnaire.
    session.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    q = session.scalars(
        select(Questionnaire).where(
            Questionnaire.workspace_id == workspace_id,
            Questionnaire.source == "csf",
            Questionnaire.mapping.contains(mapping),
        )
    ).first()
    if q is None:
        q = Questionnaire(workspace_id=workspace_id, filename=FILENAME, source="csf", mapping=mapping)
        session.add(q)
        session.flush()
        session.add_all(
            Item(
                workspace_id=workspace_id,
                questionnaire_id=q.id,
                position=n,
                row_ref=o.id,
                code=o.id,
                csf_id=o.id,
                topic=o.category,
                question=item_input(o).question,
            )
            for n, o in enumerate(outcomes, 1)
        )
    session.commit()
    return q


def part_inputs(o: Outcome) -> tuple[ItemInput, ...]:
    """Each part as its own item (CSF spec 5.2, amended); the key names the outcome and the part's place."""
    return tuple(ItemInput(f"{o.id}#{n}", p, o.category) for n, p in enumerate(o.parts, 1))


def evidence(session: Session, workspace_id: uuid.UUID, item: ItemInput) -> Retrieval:
    """What one part of a Checked outcome is judged on (Ruling 9, spec 5.3 "checked against documents"): its
    retrieval without the visitor's stored answers, each dropped with reason 'statement' before any model sees
    it. An answer reaches a Checked outcome only as a suggestion the visitor accepts (Plan 6B)."""
    r = retrieve(session, workspace_id, item.question, item.topic)
    said = [p for p in r.passages if p.doc.kind == "statement"]
    return Retrieval(
        tuple(p for p in r.passages if p.doc.kind != "statement"),
        r.dropped + tuple(Dropped(p.chunk_id, p.doc.id, p.doc.filename, "statement") for p in said),
    )


def part_label(r: ItemResult) -> PartLabel:
    """A part's label: its decide output through spec 5.3's table."""
    return _CHECKED[(r.decision.label, r.decision.value)]


def combine(labels: Sequence[PartLabel]) -> PartLabel:
    """An outcome's label from its parts' labels (CSF spec 5.3, amended); the first rule that applies wins:
    any part disagreeing is Documents disagree; any part stated No is Not met; every part Covered is Covered;
    every part Gap is Gap; any other mix is Partly covered. One part maps to itself."""
    if not labels:
        raise ValueError("an outcome needs at least one part")
    if "documents_disagree" in labels:
        return "documents_disagree"
    if "not_met" in labels:
        return "not_met"
    if all(x == "covered" for x in labels):
        return "covered"
    if all(x == "gap" for x in labels):
        return "gap"
    return "partly_covered"


def _unique[T](items: Iterable[T], key: Callable[[T], object]) -> tuple[T, ...]:
    """The first of each key, in order."""
    seen: dict[object, T] = {}
    for x in items:
        seen.setdefault(key(x), x)
    return tuple(seen.values())


def _numbers(ns: list[int]) -> str:
    return f"part {ns[0]}" if len(ns) == 1 else "parts " + ", ".join(map(str, ns))


def explain(o: Outcome, parts: Sequence[ItemResult]) -> str:
    """The outcome's explanation (CSF spec 5.3, amended), by code with no model call: the part numbers by
    label, then each part that decided the combined label as its question and its own template answer, so a
    quote always stands beside the stance it was judged with and a stated No is never shown over yes lines."""
    labels = [part_label(r) for r in parts]
    deciding = _DECIDING[combine(labels)]
    groups = [
        f"{word}: {_numbers([n for n, x in enumerate(labels, 1) if x == label])}."
        for label, word in PART_WORDS.items()
        if label in labels
    ]
    answers = [
        f"{q} {template_answer(r.decision)}"
        for q, r, x in zip(o.parts, parts, labels, strict=True)
        if x in deciding
    ]
    return " ".join([*groups, *answers])


def aggregate(o: Outcome, parts: Sequence[ItemResult]) -> ItemResult:
    """One result for the outcome from its parts' results, in part order (CSF spec 5.3, amended). The Decision
    is a display record: the label by `combine`; every part's citations (each keeping its own part's stance),
    drops and passages without duplicates; the first disagreeing part's conflict; the parts' scope notes;
    decide's confidence rule (spec 6.7 rule 9) over the merged drops. The explanation is `explain`.
    Per-passage stances stay with the parts (`check_parts`): their indices point into each part's own
    passages."""
    label, value = _DECIDE[combine([part_label(r) for r in parts])]
    dropped = _unique(
        (d for r in parts for d in r.decision.dropped), lambda d: (d.chunk_id, d.reason, d.quote)
    )
    confidence = CONFIDENCE[label] - (0.2 if any(d.reason in QUOTE_FAILURES for d in dropped) else 0.0)
    decision = Decision(
        label,
        value,
        _unique(
            (c for r in parts for c in r.decision.citations),
            lambda c: (c.document_id, c.line_start, c.line_end, c.quote, c.stance),
        ),
        dropped,
        next((r.decision.conflict for r in parts if r.decision.conflict is not None), None),
        " ".join(_unique((n for r in parts if (n := r.decision.scope_note)), lambda n: n)) or None,
        round(max(confidence, 0.0), 2),
    )
    retrieval = Retrieval(
        _unique((p for r in parts for p in r.retrieval.passages), lambda p: p.chunk_id),
        _unique((d for r in parts for d in r.retrieval.dropped), lambda d: (d.chunk_id, d.reason, d.quote)),
    )
    return ItemResult(
        item_input(o),
        retrieval,
        (),
        decision,
        Draft(explain(o, parts), "template"),
        round(sum(r.cost_usd for r in parts), 6),
        sum(r.latency_ms for r in parts),
    )


def _without_draft(spend: Spend) -> Spend:
    """A part's own draft is never shown. Refusing its budget makes write_draft return the template with no
    model call and nothing spent; the outcome's explanation is `explain`. Pinned by
    tests/test_csf_parts.py::test_each_part_is_spent_and_judged_with_no_draft_and_no_open_transaction: if
    write_draft ever raises on a refused budget, that test fails before any CSF run does (M7)."""
    return lambda step: step != "draft" and spend(step)


def check_part(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    n: int,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult:
    """Part `n` (1-based) of a Checked outcome through the ordinary pipeline, on documents only, its draft
    refused before anything is spent (CSF spec 5.2): one stance call when it has passages, none otherwise."""
    item = part_inputs(o)[n - 1]
    retrieval = evidence(session, workspace_id, item)
    return answer_retrieved(session, workspace_id, item, retrieval, llm, models, _without_draft(spend))


def check_parts(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> list[ItemResult]:
    """The parts' own results, in part order (CSF spec 5.2, amended): each part through the ordinary pipeline
    (answer_retrieved spends before each model call and commits before it, so no transaction is open across
    one) on documents only (`evidence`). Ask me: [] with no retrieval and no model call (it has no parts). Not
    checked: never part of a run."""
    if o.tier == "not_checked":
        raise ValueError(f"{o.id} is {NOT_CHECKED}")
    return [check_part(session, workspace_id, o, n, llm, models, spend) for n in range(1, len(o.parts) + 1)]


def _cited(rows: Sequence[Mapping[str, Any]]) -> tuple[Citation, ...]:
    return tuple(Citation(**c) for c in rows)


def _side(s: Mapping[str, Any]) -> ConflictSide:
    return ConflictSide(
        s["stance"], _cited(s["citations"]), date.fromisoformat(s["date"]) if s["date"] else None
    )


def part_result(o: Outcome, n: int, raw: Mapping[str, Any]) -> ItemResult:
    """Part `n` rebuilt from its stored record with no model call (app.runs stores each part as it lands, CSF
    spec 5.7): what `aggregate`, `explain` and the inspector need. The passages are not rebuilt; their chunk
    ids stay in raw["chunk_ids"]. Keys beyond `runs._raw`'s (the question, the judge) are ignored."""
    c = raw["conflict"]
    conflict = None
    if c:
        first, second = (_side(s) for s in c["sides"])
        conflict = Conflict(c["rule"], (first, second))
    decision = Decision(
        raw["label"],
        raw["value"],
        _cited(raw["citations"]),
        tuple(Dropped(**d) for d in raw["dropped"]),
        conflict,
        raw["scope_note"],
        raw["confidence"],
    )
    return ItemResult(
        part_inputs(o)[n - 1],
        Retrieval((), tuple(Dropped(**d) for d in raw["retrieval_dropped"])),
        tuple(Stance(**s) for s in raw["stances"]),
        decision,
        Draft(raw["text"], "template"),
        0.0,
        0,
    )


def check_outcome(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult | None:
    """One outcome of a gap-check run (CSF spec 5.2-5.5, amended): Checked, its parts combined (`aggregate`);
    Ask me, None, with no retrieval and no model call (the visitor answers it through ask_queue and
    store_statement); not checked, ValueError."""
    parts = check_parts(session, workspace_id, o, llm, models, spend)
    return aggregate(o, parts) if parts else None


def ask_queue(outcomes: Sequence[Outcome], asked: Mapping[str, int]) -> list[QueueEntry]:
    """Questions for you (CSF spec 5.4): the Ask-me outcomes, through the interview planner, so an outcome
    already asked (`asked[id] >= 1`) is not queued again. An answer is stored with store_statement (redacted)
    and shows Confirmed by you through gap_label, citing that statement."""
    return plan_queue(
        [
            OpenItem(item_input(o), "unknown", asked.get(o.id, 0), o.question or "")
            for o in outcomes
            if o.tier == "ask"
        ]
    )

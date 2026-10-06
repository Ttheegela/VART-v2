"""NIST CSF 2.0 gap check (CSF spec 4-6): the bundled outcomes, scopes, and the gap labels, a display
mapping over decide's output (decide itself does not change).
data/csf/csf-2.0.json is built and drift-tested by datakit/csf.py; the app only reads it."""

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import ItemInput, ItemLabel, ItemResult, OpenItem, QueueEntry, Spend, Value
from app.db.models import Item, Questionnaire, Workspace
from app.interview import plan_queue
from app.llm.client import LLMClient
from app.pipeline import answer_item

DATA = Path(__file__).resolve().parent.parent / "data" / "csf" / "csf-2.0.json"
Tier = Literal["checked", "ask", "not_checked"]
Scope = Literal["core", "govern", "identify", "protect", "detect", "respond", "recover"]
SCOPES: tuple[str, ...] = get_args(Scope)
GapLabel = Literal[
    "covered", "partly_covered", "not_met", "documents_disagree", "gap", "confirmed_by_you", "not_answered"
]
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
_CHECKED: dict[tuple[str, str | None], GapLabel] = {  # CSF spec 5.3
    ("verified", "Yes"): "covered",
    ("partial", "Partial"): "partly_covered",
    ("verified", "No"): "not_met",
    ("conflict", None): "documents_disagree",
    ("unknown", None): "gap",
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


@dataclass(frozen=True)
class Framework:
    version: str
    retrieved: str
    outcomes: tuple[Outcome, ...]

    def get(self, csf_id: str) -> Outcome:
        return {o.id: o for o in self.outcomes}[csf_id]


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
    rows = [[o.id, o.tier, o.question, o.category] for o in outcomes]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def questionnaire_for(session: Session, workspace_id: uuid.UUID, scope: str) -> Questionnaire:
    """The workspace's built-in CSF questionnaire for `scope` (CSF spec 6), created on first use with one
    item per Checked and Ask-me outcome in scope. It is reused only while the CSF data behind it is the same
    (version, retrieval date, scope and a digest of the items), so a deploy that changes the tiers or a
    question gives the next run new items instead of stale ones. Found by those mapping keys (JSONB
    containment), so a key added to the mapping later does not hide it. Commits."""
    outcomes = in_scope(scope)
    fw = framework()
    mapping = {
        "csf_version": fw.version,
        "retrieved": fw.retrieved,
        "scope": scope,
        "digest": _digest(outcomes),
    }
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


def check_outcome(
    session: Session,
    workspace_id: uuid.UUID,
    o: Outcome,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult | None:
    """One outcome of a gap-check run (CSF spec 5.2-5.5). Checked: answer_item unchanged (it spends before
    each model call and holds no transaction across one). Ask me: None, with no retrieval and no model call;
    the visitor answers it through ask_queue and store_statement. Not checked: never part of a run."""
    if o.tier == "checked":
        return answer_item(session, workspace_id, item_input(o), llm, models, spend)
    if o.tier == "ask":
        return None
    raise ValueError(f"{o.id} is {NOT_CHECKED}")


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

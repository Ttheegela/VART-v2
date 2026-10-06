"""NIST CSF 2.0 gap check (CSF spec 4-6): the bundled outcomes, scopes, and the gap labels, a display
mapping over decide's output (decide itself does not change).
data/csf/csf-2.0.json is built and drift-tested by datakit/csf.py; the app only reads it."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from app.contracts import ItemInput, ItemLabel, Value

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

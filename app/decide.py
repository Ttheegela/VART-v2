"""Decide (spec 6.7): pure rules that turn the model's stances into a label, citations and a confidence.
No model call and no database, so a metadata override re-runs it on stances already collected. Rules apply
in the spec's order; tests/test_decide.py covers every branch, tests/test_decide_properties.py the
invariants."""

from collections.abc import Sequence
from datetime import date

from app.contracts import (
    Citation,
    Conflict,
    ConflictSide,
    Decision,
    Dropped,
    DropReason,
    Label,
    Passage,
    Stance,
    Value,
)
from app.patterns import NEGATION
from app.text import contains, normalize

MIN_WORDS, MAX_WORDS = 3, 30  # a text quote is 3 to 30 words (adversary F9); a record quote at most 30
CONFIDENCE = {"verified": 0.9, "partial": 0.6, "conflict": 0.3, "unknown": 0.0}
QUOTE_FAILURES: frozenset[DropReason] = frozenset({"containment", "quote-length", "record-field"})
SCOPE_WORDS = {
    "internal-systems": "internal systems",
    "customer-product": "the customer product",
    "production": "the production environment",
    "employees": "employees",
    "vendors-and-contractors": "vendors and contractors",
}
Pair = tuple[Passage, Citation]


def whole_fields(line: str, quote: str) -> bool:
    """True when the quote is one or more complete 'Header: value' fields of a record line (adversary F10):
    a header without its value cannot carry a claim."""
    text, needle = normalize(line), normalize(quote).rstrip(";").rstrip()
    if ": " not in needle:
        return False
    start = text.find(needle)
    while start != -1:
        end = start + len(needle)
        if (start == 0 or text.startswith("; ", start - 2)) and (
            end == len(text) or text.startswith("; ", end)
        ):
            return True
        start = text.find(needle, start + 1)
    return False


def check_quote(p: Passage, quote: str) -> tuple[int, None] | tuple[None, DropReason]:
    """Rule 1: the document line that holds the quote, or why the quote fails. A quote must sit inside one
    line of the passage (adversary F8)."""
    words = len(normalize(quote).split())
    if words > MAX_WORDS or (not p.record and words < MIN_WORDS):
        return None, "quote-length"
    for i, line in enumerate(p.lines):
        if contains(line, quote):
            if p.record and not whole_fields(line, quote):
                return None, "record-field"
            return p.line_start + i, None
    return None, "containment"


def _gate(p: Passage) -> DropReason | None:
    """Rule 2: passages that are never evidence."""
    if not p.doc.evidence_allowed:
        return "not-evidence"
    if "placeholder" in p.flags:
        return "placeholder"
    if "injection" in p.flags:
        return "injection"
    return None


def _date(p: Passage) -> date | None:
    return p.as_of or p.doc.effective_date


def _side(stance: str, pairs: list[Pair]) -> ConflictSide:
    dates = [d for p, _ in pairs if (d := _date(p)) is not None]
    return ConflictSide(
        "yes" if stance == "yes" else "no", tuple(c for _, c in pairs), max(dates, default=None)
    )


def _conflict(yes: list[Pair], no: list[Pair]) -> Conflict:
    """Rule 6: a dated record newer than every dated document on the other side is the 'date' rule, newer
    side first; anything else is 'documents-disagree'."""
    for newer, older in ((yes, no), (no, yes)):
        records = [p.as_of for p, _ in newer if p.record and p.as_of is not None]
        others = [d for p, _ in older if (d := _date(p)) is not None]
        if records and others and max(records) > max(others):
            return Conflict(
                "date",
                (
                    _side("yes" if newer is yes else "no", newer),
                    _side("yes" if older is yes else "no", older),
                ),
            )
    return Conflict("documents-disagree", (_side("yes", yes), _side("no", no)))


def _scope_note(yes: list[Pair], no: list[Pair]) -> str:
    def part(word: str, pairs: list[Pair]) -> str:
        scopes = sorted({s for p, _ in pairs if (s := p.doc.scope)})
        names = sorted({p.doc.filename for p, _ in pairs})
        return f"{word} for {' and '.join(SCOPE_WORDS.get(s, s) for s in scopes)} ({', '.join(names)})"

    return f"{part('Yes', yes)}; {part('no', no)}."


def decide(
    passages: Sequence[Passage], stances: Sequence[Stance], dropped: Sequence[Dropped] = ()
) -> Decision:
    """`stances[i].passage` is a 1-based index into `passages`; `dropped` (from retrieval) is carried over."""
    out = list(dropped)
    kept: list[Pair] = []
    seen: set[int] = set()
    for s in stances:
        if s.passage in seen or not 1 <= s.passage <= len(passages):
            continue  # one judgement per passage; an index the prompt never showed is ignored
        seen.add(s.passage)
        if s.stance == "irrelevant":  # rule 3 (an irrelevant stance has no quote to check)
            continue
        p = passages[s.passage - 1]
        quote = s.quote.strip()  # the same text whether it is cited or dropped
        line, reason = check_quote(p, s.quote)
        reason = reason or _gate(p)
        if line is None or reason is not None:
            out.append(Dropped(p.chunk_id, p.doc.id, p.doc.filename, reason or "containment", quote))
            continue
        stance, note = s.stance, ""
        if stance == "yes" and NEGATION.search(normalize(s.quote)):  # rule 4, on the quote (Plan 1B Ruling 9)
            stance, note = "partial", "negation"
        kept.append((p, Citation(p.chunk_id, p.doc.id, p.doc.filename, line, line, quote, stance, note)))
    citations = tuple(c for _, c in kept)
    yes = [(p, c) for p, c in kept if c.stance == "yes"]
    no = [(p, c) for p, c in kept if c.stance == "no"]
    label: Label
    value: Value | None
    conflict: Conflict | None = None
    scope_note: str | None = None
    if not kept:
        label, value = "unknown", None
    elif yes and no and len({c.document_id for _, c in yes + no}) >= 2:
        yes_scopes = {p.doc.scope for p, _ in yes}
        no_scopes = {p.doc.scope for p, _ in no}
        if None not in yes_scopes | no_scopes and yes_scopes.isdisjoint(no_scopes):  # rule 5
            label, value, scope_note = "partial", "Partial", _scope_note(yes, no)
        else:  # rule 6
            label, value, conflict = "conflict", None, _conflict(yes, no)
    elif all(c.stance == "yes" for c in citations):  # rule 7
        label, value = "verified", "Yes"
    elif all(c.stance == "no" for c in citations):
        label, value = "verified", "No"
    else:
        label, value = "partial", "Partial"
    if label == "verified" and all(p.doc.status == "draft" for p, _ in kept):  # rule 8
        label, value = "partial", "Partial"
    confidence = CONFIDENCE[label] - (0.2 if any(d.reason in QUOTE_FAILURES for d in out) else 0.0)  # rule 9
    return Decision(label, value, citations, tuple(out), conflict, scope_note, round(max(confidence, 0.0), 2))

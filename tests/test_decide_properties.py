"""Spec 8: Hypothesis property tests for decide. Small sentence pool, random stances and quotes (some true,
some invented), random metadata; every case must keep these invariants."""

from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from app.contracts import DocInfo, Passage, Stance
from app.decide import decide
from app.text import contains

LINES = [
    "User access is reviewed quarterly.",
    "MFA is not yet enforced for administrators.",
    "System: Okta; Status: Overdue",
    "Backups run daily and are encrypted at rest.",
    "[Company Name] reviews this policy [frequency].",
]
DOCS = st.builds(
    DocInfo,
    id=st.sampled_from(["d1", "d2", "d3"]),
    filename=st.sampled_from(["a.docx", "b.pdf", "c.xlsx"]),
    kind=st.just("policy"),
    status=st.sampled_from(["final", "draft"]),
    effective_date=st.sampled_from([None, date(2026, 1, 1), date(2026, 6, 1)]),
    scope=st.sampled_from([None, "internal-systems", "customer-product"]),
    evidence_allowed=st.booleans(),
)
FLAGS = st.lists(st.sampled_from(["negation", "placeholder", "injection"]), unique=True, max_size=2)
Case = tuple[list[Passage], list[Stance]]


@st.composite
def cases(draw: st.DrawFn) -> Case:
    passages = [
        Passage(
            f"c{i}",
            draw(DOCS),
            draw(st.integers(1, 40)),
            tuple(draw(st.lists(st.sampled_from(LINES), min_size=1, max_size=3))),
            None,
            tuple(draw(FLAGS)),
            draw(st.sampled_from([None, date(2026, 9, 1)])),
            draw(st.booleans()),
        )
        for i in range(draw(st.integers(1, 4)))
    ]
    stances = []
    for i, p in enumerate(passages, 1):
        if draw(st.booleans()):
            words = draw(st.sampled_from(p.lines)).split()
            a = draw(st.integers(0, len(words) - 1))
            b = draw(st.integers(a + 1, len(words)))
            quote = draw(st.sampled_from([" ".join(words[a:b]), " ".join(words), "an invented sentence"]))
            label = draw(st.sampled_from(["yes", "no", "partial", "irrelevant"]))
            stances.append(Stance(i, label, quote, ""))
    return passages, stances


@given(cases())
@settings(max_examples=300, deadline=None)
def test_every_cited_quote_sits_in_the_one_line_it_names(case: Case) -> None:
    passages, stances = case
    by_chunk = {p.chunk_id: p for p in passages}
    for c in decide(passages, stances).citations:
        p = by_chunk[c.chunk_id]
        assert c.line_start == c.line_end
        assert contains(p.lines[c.line_start - p.line_start], c.quote)


@given(cases())
@settings(max_examples=300, deadline=None)
def test_a_dropped_quote_never_appears_in_the_citations(case: Case) -> None:
    d = decide(*case)
    dropped = {(x.chunk_id, x.quote) for x in d.dropped}
    assert not dropped & {(c.chunk_id, c.quote) for c in d.citations}


@given(cases())
@settings(max_examples=300, deadline=None)
def test_nothing_is_cited_from_a_passage_that_is_never_evidence(case: Case) -> None:
    passages, stances = case
    by_chunk = {p.chunk_id: p for p in passages}
    for c in decide(passages, stances).citations:
        p = by_chunk[c.chunk_id]
        assert p.doc.evidence_allowed and not {"placeholder", "injection"} & set(p.flags)


@given(cases())
@settings(max_examples=300, deadline=None)
def test_adding_an_irrelevant_stance_never_changes_the_answer(case: Case) -> None:
    passages, stances = case
    before = decide(passages, stances)
    for i in range(1, len(passages) + 1):
        after = decide(passages, [*stances, Stance(i, "irrelevant", "", "")])
        assert (after.label, after.value, after.citations) == (before.label, before.value, before.citations)


@given(cases())
@settings(max_examples=300, deadline=None)
def test_a_conflict_always_has_two_sides(case: Case) -> None:
    d = decide(*case)
    if d.label == "conflict":
        assert d.conflict is not None
        assert {s.stance for s in d.conflict.sides} == {"yes", "no"}
        assert all(s.citations for s in d.conflict.sides)
    else:
        assert d.conflict is None


@given(cases())
@settings(max_examples=300, deadline=None)
def test_the_label_value_citations_and_confidence_agree(case: Case) -> None:
    d = decide(*case)
    assert bool(d.citations) == (d.label != "unknown")  # the ck_answers_cited rule, and its converse
    assert (d.value is None) == (d.label in ("unknown", "conflict"))
    assert 0.0 <= d.confidence <= 1.0

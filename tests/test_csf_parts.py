import itertools
import json
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import csf, runs
from app.contracts import (
    BudgetExhausted,
    Citation,
    Conflict,
    ConflictSide,
    Decision,
    DocInfo,
    Draft,
    Dropped,
    ItemInput,
    ItemResult,
    Passage,
    Retrieval,
)
from app.db.models import LlmUsage
from app.llm.client import LLMRequest, LLMResult
from app.services import llm_budget
from app.services.llm_budget import spender
from tests import factories as f
from tests.fakes import FakeLLM

LABELS = ("covered", "partly_covered", "not_met", "documents_disagree", "gap")
MODELS = {"stance": "m/stance", "draft": "m/draft"}
DOC = DocInfo("d1", "access-control-policy.md", "policy", "final", None, None, True)
QUOTE = "Every security incident is reviewed to find its root cause."


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _outcome(n: int) -> csf.Outcome:
    return replace(
        csf.framework().get("PR.AA-05"), parts=tuple(f"Is part {i} done?" for i in range(1, n + 1))
    )


def _part(n: int, label: str, line: int | None = None, doc: DocInfo = DOC) -> ItemResult:
    """A part's result as decide gives it: every label but Gap cites a line; a disagreement cites one line
    per side."""
    line = line or n
    p = Passage(f"c{line}", doc, line, (f"Access rule number {line} is enforced.",), None, (), None, False)
    decided, value = csf._DECIDE[label]  # type: ignore[index]
    stance = {"not_met": "no", "partly_covered": "partial"}.get(label, "yes")
    cite = Citation(p.chunk_id, doc.id, doc.filename, line, line, p.lines[0], stance)  # type: ignore[arg-type]
    cites: tuple[Citation, ...] = () if label == "gap" else (cite,)
    conflict = None
    if label == "documents_disagree":
        no = Citation(f"{p.chunk_id}n", "d9", "access-review-records.xlsx", 3, 3, "Status: Overdue", "no")
        cites = (cite, no)
        conflict = Conflict(
            "documents-disagree", (ConflictSide("yes", (cite,), None), ConflictSide("no", (no,), None))
        )
    decision = Decision(decided, value, cites, (), conflict, None, 0.9)
    item = ItemInput(f"PR.AA-05#{n}", "q", None)
    return ItemResult(item, Retrieval((p,), ()), (), decision, Draft("", "template"), 0.001, 100)


def test_every_checked_outcome_has_its_parts_and_only_checked_ones_do() -> None:
    outcomes = csf.framework().outcomes
    assert all(o.parts for o in outcomes if o.tier == "checked")
    assert all(o.parts == () for o in outcomes if o.tier != "checked")
    assert sum(len(o.parts) for o in outcomes) == 73
    o = csf.framework().get("PR.DS-11")
    assert csf.part_inputs(o)[3] == ItemInput("PR.DS-11#4", "Are backups of data tested?", "Data Security")


def test_the_decide_mapping_is_the_inverse_of_the_gap_table() -> None:
    assert {gap: pair for pair, gap in csf._CHECKED.items()} == csf._DECIDE


@pytest.mark.parametrize(
    ("labels", "want"),
    [
        (("covered",), "covered"),
        (("covered", "covered", "covered"), "covered"),
        (("gap", "gap"), "gap"),
        (("covered", "gap"), "partly_covered"),
        (("partly_covered",), "partly_covered"),
        (("covered", "partly_covered"), "partly_covered"),
        (("covered", "not_met"), "not_met"),  # a stated No outranks evidenced parts
        (("partly_covered", "not_met", "gap"), "not_met"),
        (("not_met", "documents_disagree"), "documents_disagree"),  # a disagreement outranks a stated No
        (("covered", "documents_disagree", "gap"), "documents_disagree"),
    ],
)
def test_parts_combine_in_the_spec_order(labels: tuple[str, ...], want: str) -> None:
    assert csf.combine(labels) == want  # type: ignore[arg-type]


@pytest.mark.parametrize("n", [1, 2, 3])
def test_every_mix_of_part_labels_follows_the_precedence(n: int) -> None:
    for labels in itertools.product(LABELS, repeat=n):
        got = csf.combine(labels)  # type: ignore[arg-type]
        assert (got == "documents_disagree") == ("documents_disagree" in labels), labels
        assert (got == "not_met") == ("not_met" in labels and "documents_disagree" not in labels), labels
        assert (got == "covered") == (set(labels) == {"covered"}), labels
        assert (got == "gap") == (set(labels) == {"gap"}), labels
        assert n > 1 or got == labels[0]  # one part maps to itself: spec 5.3's table


def test_an_outcome_without_parts_has_no_label() -> None:
    with pytest.raises(ValueError, match="at least one part"):
        csf.combine([])


@pytest.mark.parametrize("n", [1, 2, 3])
def test_no_outcome_is_covered_or_partly_without_a_citation(n: int) -> None:
    o = _outcome(n)
    for labels in itertools.product(LABELS, repeat=n):
        r = csf.aggregate(o, [_part(i, x) for i, x in enumerate(labels, 1)])
        shown = csf.gap_label(o, r.decision.label, r.decision.value)
        assert shown == csf.combine(labels), labels  # type: ignore[arg-type]
        assert bool(r.decision.citations) == (shown != "gap"), labels  # ck_answers_cited


def test_citations_and_passages_are_the_parts_union_without_duplicates() -> None:
    o = _outcome(3)
    r = csf.aggregate(o, [_part(1, "covered", 4), _part(2, "covered", 4), _part(3, "partly_covered", 7)])
    assert [(c.line_start, c.stance) for c in r.decision.citations] == [(4, "yes"), (7, "partial")]
    assert [p.chunk_id for p in r.retrieval.passages] == ["c4", "c7"]
    assert (r.item, r.stances, r.cost_usd, r.latency_ms) == (csf.item_input(o), (), 0.003, 300)
    same_line = csf.aggregate(_outcome(2), [_part(1, "covered", 4), _part(2, "partly_covered", 4)])
    assert [c.stance for c in same_line.decision.citations] == ["yes", "partial"]  # M2: stance is in the key


def test_a_quote_failure_in_any_part_lowers_the_confidence_as_decide_does() -> None:
    dropped = (Dropped("c9", "d1", DOC.filename, "containment", "a quote not in the line"),)
    failed = _part(2, "covered")
    failed = replace(failed, decision=replace(failed.decision, dropped=dropped))
    r = csf.aggregate(_outcome(2), [_part(1, "covered"), failed])
    assert (r.decision.confidence, r.decision.dropped) == (0.7, dropped)
    assert csf.aggregate(_outcome(2), [_part(1, "covered"), _part(2, "covered")]).decision.confidence == 0.9


def test_a_stated_no_is_quoted_from_its_own_part_never_over_yes_lines() -> None:
    """Adversary C2: parts covered in documents A and B and stated No in C; the outcome is Not met, and its
    explanation quotes C's line only, after the group line."""
    a, b, c = (replace(DOC, id=x, filename=f"{x}-policy.md") for x in ("a", "b", "c"))
    parts = [_part(1, "covered", doc=a), _part(2, "covered", doc=b), _part(3, "not_met", doc=c)]
    r = csf.aggregate(_outcome(3), parts)
    assert (r.decision.label, r.decision.value) == ("verified", "No")
    assert r.draft.text == (
        "Evidenced: parts 1, 2. Stated as not done: part 3. "
        'Is part 3 done? No. The c policy says: "Access rule number 3 is enforced."'
    )
    assert [x.stance for x in r.decision.citations] == ["yes", "yes", "no"]  # a display record: stances kept


def test_the_explanation_shows_only_the_deciding_parts() -> None:
    o = _outcome(3)
    r = csf.aggregate(o, [_part(1, "covered"), _part(2, "documents_disagree"), _part(3, "gap")])
    assert r.decision.conflict is not None and r.draft.source == "template"
    assert r.draft.text.startswith(
        "Evidenced: part 1. Documents disagree: part 2. No evidence: part 3."
        " Is part 2 done? The documents disagree."
    )
    assert "Is part 1 done?" not in r.draft.text
    partly = csf.aggregate(o, [_part(1, "covered"), _part(2, "partly_covered"), _part(3, "gap")])
    assert "Is part 1 done? Yes." in partly.draft.text and "Is part 2 done? Partly." in partly.draft.text
    gap = csf.aggregate(o, [_part(i, "gap") for i in (1, 2, 3)])
    assert gap.draft.text == "No evidence: parts 1, 2, 3."


def _stance(kind: str) -> str:
    quote = "" if kind == "irrelevant" else QUOTE
    return json.dumps({"passages": [{"passage": 1, "stance": kind, "quote": quote, "note": "judged"}]})


def _two_parts() -> csf.Outcome:
    return replace(
        csf.framework().get("RS.AN-03"),
        parts=(
            "Is what took place during an incident established?",
            "Is the root cause of an incident established?",
        ),
    )


def _incident_policy(s: Session) -> uuid.UUID:
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="incident-policy.docx"), line_start=3, line_end=3, text=QUOTE)
    s.commit()
    return ws.id


def test_each_part_is_spent_and_judged_with_no_draft_and_no_open_transaction(s: Session, db: Engine) -> None:
    ws = _incident_policy(s)

    class Watching(FakeLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not s.in_transaction(), f"{req.step} ran inside an open transaction"
            return super().complete(req)

    o = _two_parts()
    llm = Watching([_stance("irrelevant"), _stance("yes")])
    parts = csf.check_parts(s, ws, o, llm, MODELS, spender(s, ws))
    assert [(q.step, q.item_id) for q in llm.requests] == [("stance", "RS.AN-03#1"), ("stance", "RS.AN-03#2")]
    assert all(part in q.user for part, q in zip(o.parts, llm.requests, strict=True))
    assert [csf.part_label(p) for p in parts] == ["gap", "covered"]
    with Session(db) as other:  # each call was spent and committed first; no draft was spent
        used = other.execute(select(LlmUsage.kind, LlmUsage.calls).where(LlmUsage.workspace_id == ws)).all()
    assert [tuple(u) for u in used] == [("stance", 2)]
    r = csf.aggregate(o, parts)
    assert csf.gap_label(o, r.decision.label, r.decision.value) == "partly_covered"
    assert [c.line_start for c in r.decision.citations] == [3]
    assert r.draft.text.startswith(f"Evidenced: part 2. No evidence: part 1. {o.parts[1]} Yes.")


def test_a_refused_stance_budget_stops_the_outcome_after_the_parts_it_paid_for(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    ws = _incident_policy(s)
    llm = FakeLLM([_stance("yes")])
    with pytest.raises(BudgetExhausted):
        csf.check_outcome(s, ws, _two_parts(), llm, MODELS, spender(s, ws))
    assert [q.step for q in llm.requests] == ["stance"]


def test_a_part_filled_from_the_visitors_answer_is_confirmed_by_them_only_when_covered() -> None:
    """adversary-2 M2 (Ruling 6): a partial fill reads as the visitor's answer with its own label word, never
    as Confirmed by you."""
    o = _outcome(3)
    parts = [_part(1, "covered"), _part(2, "partly_covered"), _part(3, "gap")]
    said = csf.explain(o, parts, filled=(1, 2))
    assert said.startswith(
        "Confirmed by you: part 1. Partly evidenced in your answer: part 2. No evidence: part 3."
    )
    assert "Confirmed by you: part 2" not in csf.explain(o, parts, filled=(2,))


def test_a_stored_part_rebuilds_to_the_same_decision_and_explanation() -> None:
    o = _outcome(4)
    parts = [_part(1, "covered"), _part(2, "documents_disagree"), _part(3, "not_met"), _part(4, "gap")]
    d = parts[1].decision
    assert d.conflict is not None  # a dated side survives the JSON round trip
    side = replace(d.conflict.sides[0], date=date(2026, 9, 15))
    parts[1] = replace(
        parts[1], decision=replace(d, conflict=replace(d.conflict, sides=(side, d.conflict.sides[1])))
    )
    stored = [
        json.loads(json.dumps({"question": q, **runs._raw(r)})) for q, r in zip(o.parts, parts, strict=True)
    ]
    rebuilt = [csf.part_result(o, n, raw) for n, raw in enumerate(stored, 1)]
    assert [r.decision for r in rebuilt] == [r.decision for r in parts]
    assert [r.item for r in rebuilt] == list(csf.part_inputs(o))
    assert csf.aggregate(o, rebuilt).decision == csf.aggregate(o, parts).decision
    assert csf.aggregate(o, rebuilt).draft.text == csf.aggregate(o, parts).draft.text


def test_check_part_runs_one_part_alone(s: Session) -> None:
    ws = _incident_policy(s)
    llm = FakeLLM([_stance("yes")])
    r = csf.check_part(s, ws, _two_parts(), 2, llm, MODELS, spender(s, ws))
    assert [(q.step, q.item_id) for q in llm.requests] == [("stance", "RS.AN-03#2")]
    assert csf.part_label(r) == "covered"


def test_the_current_mapping_names_the_scope_and_its_data() -> None:
    m = csf.current_mapping("recover")
    assert (m["csf_version"], m["retrieved"], m["scope"]) == ("2.0", "2026-10-05", "recover")
    assert m["digest"] != csf.current_mapping("core")["digest"]
    with pytest.raises(ValueError, match="unknown scope"):
        csf.current_mapping("everything")

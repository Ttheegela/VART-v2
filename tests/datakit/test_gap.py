from collections import Counter
from datetime import date

import pytest

from app.classify import rules
from app.contracts import DocMeta
from app.csf import framework, gap_label
from datakit import gap
from datakit.extract import lines_of
from datakit.schemas import Facts
from datakit.validate import STAGES, check_facts


def _labels() -> dict[str, str | None]:
    facts, g = gap.load("dev")
    return {
        k.code: gap_label(framework().get(k.code), k.expected_label, k.expected_value)
        for k in gap.derive_gap(facts, g).items
    }


def test_the_gap_stage_passes_on_the_dev_pack() -> None:
    assert STAGES["gap"]("dev") == []


def test_the_key_plants_what_the_spec_asks() -> None:
    labels = _labels()
    assert len(labels) == 31 and set(labels) == {o.id for o in gap.checked()}
    by_label: dict[str | None, set[str]] = {}
    for code, label in labels.items():
        by_label.setdefault(label, set()).add(code)
    assert by_label["documents_disagree"] == {"PR.AA-05", "DE.AE-06"}
    assert by_label["not_met"] == {"ID.RA-02", "DE.AE-07"}
    assert by_label["gap"] == {"ID.AM-03", "PR.AA-06", "PR.IR-04"}
    assert by_label["partly_covered"] == {"PR.AA-03", "RS.MA-01", "RS.CO-02"}
    assert {"RS.AN-03", "RS.MI-01"} <= by_label["covered"]
    assert Counter(labels.values())["covered"] == 21


def test_trap_outcomes_are_never_expected_covered() -> None:
    facts, g = gap.load("dev")
    f = gap.merged(facts, g)
    control = {m.csf_id: m.control for m in g.outcomes}
    sources = {c: gap.trap_sources(f, control[c]) for c in control}
    assert {c: s for c, s in sources.items() if s} == {
        "ID.RA-02": {"planned"},
        "DE.AE-07": {"planned"},
        "RS.MA-01": {"draft"},
        "RS.CO-02": {"draft", "template"},
        "PR.IR-04": {"template"},
    }
    labels = _labels()
    assert all(labels[c] != "covered" for c, s in sources.items() if s)


def test_every_checked_outcome_has_cited_evidence_or_is_an_honest_gap() -> None:
    facts, g = gap.load("dev")
    for k in gap.derive_gap(facts, g).items:
        label = gap_label(framework().get(k.code), k.expected_label, k.expected_value)
        assert bool(k.evidence) == (label != "gap"), k.code


def test_the_dev_keys_and_fact_sheet_do_not_change() -> None:
    facts, g = gap.load("dev")
    assert STAGES["keys"]("dev") == []  # vsq-a and mvsp-b are derived from the dev sheet alone
    assert not {d.id for d in g.documents} & {d.id for d in facts.documents}


def test_a_planned_only_statement_must_be_a_negated_no_in_a_final_document() -> None:
    facts, g = gap.load("dev")
    data = gap.merged(facts, g).model_dump()
    for s in data["statements"]:
        if s["id"] == "sip-threat-intel-sources":
            s["stance"], s["flags"] = "partial", []
    assert (
        "trap G2: planned-only statements must be flagged negation, stance no, in a final document"
        in check_facts(Facts.model_validate(data))
    )


def test_an_unmapped_checked_outcome_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    facts, g = gap.load("dev")
    short = g.model_copy(update={"outcomes": g.outcomes[1:]})
    monkeypatch.setattr(gap, "load", lambda pack: (facts, short))
    assert gap.check("dev") == [f"Checked outcome {g.outcomes[0].csf_id} has no control"]


def test_the_improvement_plan_is_classified_by_rules_alone() -> None:
    facts, g = gap.load("dev")
    spec = g.documents[0]
    meta, sure = rules("md", lines_of(gap.doc_path("dev", g, spec)))
    assert sure and meta == DocMeta("plan", "final", date(2026, 7, 1), None, True, "rule")

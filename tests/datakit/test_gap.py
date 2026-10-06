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
    assert by_label["partly_covered"] == {
        "PR.AA-03",
        "RS.MA-01",
        "RS.CO-02",
        "PR.DS-02",
        "PR.DS-11",
        "PR.IR-03",
        "ID.AM-05",
        "ID.AM-08",
        "GV.PO-02",
        "PR.AA-01",
        "PR.PS-02",
        "PR.PS-06",
    }
    assert {"RS.AN-03", "RS.MI-01"} <= by_label["covered"]
    assert Counter(labels.values())["covered"] == 12


def test_trap_outcomes_are_never_expected_covered() -> None:
    facts, g = gap.load("dev")
    f = gap.merged(facts, g)
    control = {m.csf_id: m.control for m in g.outcomes}
    sources = {c: gap.trap_sources(f, control[c]) for c in control}
    assert {c: s for c, s in sources.items() if s} == {
        "ID.RA-02": {"planned"},
        "DE.AE-07": {"planned"},
        "RS.MA-01": {"draft"},
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


def test_a_template_gap_does_not_count_as_an_honest_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 5 review carry: PR.IR-04 is a Gap only because its one source is a template; with ID.AM-03
    mapped to a covered control, one honest Gap is left, and the spec asks for two."""
    facts, g = gap.load("dev")
    outcomes = tuple(
        o.model_copy(update={"control": "sso"}) if o.csf_id == "ID.AM-03" else o for o in g.outcomes
    )
    monkeypatch.setattr(gap, "load", lambda pack: (facts, g.model_copy(update={"outcomes": outcomes})))
    assert "only 1 honest gap outcome(s) planted, need 2" in gap.check("dev")


def test_a_label_override_changes_the_derived_label() -> None:
    facts, g = gap.load("dev")
    plain = g.model_copy(update={"outcomes": tuple(o.model_copy(update={"label": None}) for o in g.outcomes)})
    before = {k.code: k.expected_label for k in gap.derive_gap(facts, plain).items}
    after = {k.code: k.expected_label for k in gap.derive_gap(facts, g).items}
    changed = {c for c in after if after[c] != before[c]}
    assert changed == {
        "PR.DS-02",
        "PR.DS-11",
        "PR.IR-03",
        "ID.AM-05",
        "ID.AM-08",
        "GV.PO-02",
        "PR.AA-01",
        "PR.PS-02",
        "PR.PS-06",
    }
    assert all(before[c] == "verified" and after[c] == "partial" for c in changed)


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_a_label_override_without_its_missing_parts_fails_validation(
    monkeypatch: pytest.MonkeyPatch, missing: str | None
) -> None:
    facts, g = gap.load("dev")
    outcomes = tuple(
        o.model_copy(update={"missing": missing}) if o.csf_id == "PR.DS-11" else o for o in g.outcomes
    )
    monkeypatch.setattr(gap, "load", lambda pack: (facts, g.model_copy(update={"outcomes": outcomes})))
    assert "outcome PR.DS-11: a label override needs missing" in gap.check("dev")


def test_the_per_part_rejudge_is_in_the_key() -> None:
    """Ruling 19: PR.DS-01 stays Covered with its integrity line as key evidence (and, Ruling 20, its
    availability line); PR.DS-02 is Partly covered, availability in transit missing, with its integrity line
    as key evidence."""
    facts, g = gap.load("dev")
    keys = {k.code: k for k in gap.derive_gap(facts, g).items}
    evidence = {c: {(e.doc, e.quote) for e in keys[c].evidence} for c in ("PR.DS-01", "PR.DS-02")}
    assert ("lmp", "Improper alteration or loss of sensitive information.") in evidence["PR.DS-01"]
    assert ("bcpol", "Kestrelyn performs daily backups of all production databases.") in evidence["PR.DS-01"]
    scope = (
        "This policy applies to all Kestrelyn systems that store, transmit, or process sensitive information."
    )
    assert ("lmp", scope) in evidence["PR.DS-02"]
    assert (keys["PR.DS-01"].expected_label, keys["PR.DS-02"].expected_label) == ("verified", "partial")


@pytest.mark.parametrize(
    ("update", "problem"),
    [
        ({"missing_parts": ()}, "outcome PR.DS-11: a label override needs missing_parts"),
        ({"missing_parts": (9,)}, "outcome PR.DS-11: no part 9"),
        ({"label": None, "missing": None}, "outcome PR.DS-11: missing_parts without a label override"),
    ],
)
def test_an_override_names_the_parts_it_misses(
    monkeypatch: pytest.MonkeyPatch, update: dict[str, object], problem: str
) -> None:
    facts, g = gap.load("dev")
    outcomes = tuple(o.model_copy(update=update) if o.csf_id == "PR.DS-11" else o for o in g.outcomes)
    monkeypatch.setattr(gap, "load", lambda pack: (facts, g.model_copy(update={"outcomes": outcomes})))
    assert problem in gap.check("dev")


def test_a_planted_conflict_must_be_visible_to_a_part_without_a_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adversary C1: 'performed annually' is a no only against a question that says quarterly; a CSF part
    states no interval, so trap X1 cannot be a CSF disagreement. The two real ones pass: DE.AE-06's no side is
    negated, PR.AA-05's is an overdue record row."""
    facts, g = gap.load("dev")
    remap = {"control": "backup-restore-test", "label": None, "missing": None, "missing_parts": ()}
    outcomes = tuple(o.model_copy(update=remap) if o.csf_id == "PR.DS-11" else o for o in g.outcomes)
    monkeypatch.setattr(gap, "load", lambda pack: (facts, g.model_copy(update={"outcomes": outcomes})))
    found = gap.check("dev")
    assert "PR.DS-11: conflict X1 rests on a thresholded no the CSF part cannot see" in found
    assert not [p for p in found if p.startswith(("PR.AA-05:", "DE.AE-06:"))]

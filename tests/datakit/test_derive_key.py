import shutil
from collections import Counter
from pathlib import Path

import pytest

from datakit import derive_key, validate
from datakit.derive_key import derive, derive_item
from datakit.schemas import (
    DocSpec,
    Facts,
    Key,
    KeyItem,
    Selection,
    SelectionItem,
    Statement,
    Trap,
    dump_yaml,
    load_yaml,
)
from datakit.validate import DATA, STAGES


def _facts() -> Facts:
    return load_yaml(DATA / "dev" / "facts.yaml", Facts)


def _selection(name: str) -> Selection:
    return load_yaml(DATA / "questionnaires" / f"{name}.selection.yaml", Selection)


def _key(name: str) -> Key:
    return derive(_facts(), _selection(name))


def _by_control(name: str) -> dict[str, list[KeyItem]]:
    items = {i.code: i.control for i in _selection(name).items}
    out: dict[str, list[KeyItem]] = {}
    for k in _key(name).items:
        out.setdefault(items[k.code], []).append(k)
    return out


# the control each trap is planted on: the vsq-a items asking about it carry the expected outcome
CONFLICTS = {
    "D1": "access-review",
    "D2": "cloud-only",
    "D3": "data-residency",
    "X1": "backup-restore-test",
    "X2": "log-retention",
}
SCOPE_PARTIALS = {"S1": "mfa", "S2": "background-checks"}
HONEST_NOS = {
    "H1": "iso27001",
    "H2": "ml-training",
    "H3": "bug-bounty",
    "H4": "dast",
    "H5": "customer-pentest",
}
DRAFT_ONLY = {"R1": "laptop-encryption", "R2": "ir-plan"}


def test_planted_traps_come_out_as_designed() -> None:
    k = _by_control("vsq-a")
    for trap, control in CONFLICTS.items():
        assert all(
            trap in x.traps and x.expected_label == "conflict" and x.expected_value is None
            for x in k[control]
        ), trap
        assert all(x.conflict_trap == trap for x in k[control]), trap
    for trap, control in SCOPE_PARTIALS.items():
        assert all(
            trap in x.traps and x.expected_label == "partial" and x.scope_note_expected for x in k[control]
        ), trap
    for trap, control in HONEST_NOS.items():
        assert all(
            trap in x.traps
            and x.expected_label == "verified"
            and x.expected_value == "No"
            and x.honest_negative
            for x in k[control]
        ), trap
    for trap, control in DRAFT_ONLY.items():
        assert all(trap in x.traps and x.expected_label == "partial" for x in k[control]), trap
    must_ask = [t for t in _facts().traps if t.kind == "must_ask"]
    assert len(must_ask) == 13
    for trap in must_ask:
        for control in trap.controls:
            assert all(
                trap.id in x.traps and x.expected_label == "unknown" and x.must_ask for x in k[control]
            ), trap.id
    assert all(x.expected_label == "verified" and x.expected_value == "Yes" for x in k["pentest"])
    assert [x.fills for x in k["cyber-insurance"]] == [("VSQ-59",)]
    assert [x.fills for x in k["security-contact"]] == [("VSQ-61",)]


TALLIES = {
    "vsq-a": {"Yes": 30, "No": 5, "Partial": 9, "Conflict": 7, "Unknown": 13},
    "mvsp-b": {"Yes": 17, "No": 1, "Partial": 1, "Conflict": 0, "Unknown": 6},
}


@pytest.mark.parametrize("name", TALLIES)
def test_the_outcome_tallies_are_pinned(name: str) -> None:
    items = _key(name).items
    got = Counter(
        i.expected_value if i.expected_label == "verified" else i.expected_label.title() for i in items
    )
    assert got == Counter(TALLIES[name])
    assert len(items) == len(_selection(name).items)


def test_no_key_evidence_comes_from_non_evidence_or_trap_sentences() -> None:
    facts = _facts()
    banned = {s.text for s in facts.statements if {"placeholder", "injection"} & set(s.flags)}
    for name in ("vsq-a", "mvsp-b"):
        for item in _key(name).items:
            for ev in item.evidence:
                assert facts.doc(ev.doc).evidence_allowed and ev.quote not in banned


def test_the_committed_keys_match_the_derivation() -> None:
    for name in ("vsq-a", "mvsp-b"):
        assert load_yaml(DATA / "dev" / "key" / f"{name}.yaml", Key) == _key(name), name


def _copy_of_the_data(root: Path) -> Path:
    """The pieces derive_key.main reads (the fact sheet and the selections), under a fake repository root."""
    shutil.copytree(DATA / "questionnaires", root / "data" / "questionnaires")
    (root / "data" / "dev").mkdir(parents=True)
    shutil.copy(DATA / "dev" / "facts.yaml", root / "data" / "dev" / "facts.yaml")
    return root / "data" / "dev"


def test_main_writes_the_committed_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dev = _copy_of_the_data(tmp_path)
    monkeypatch.setattr(derive_key, "ROOT", tmp_path)
    derive_key.main("dev")
    for name in ("vsq-a", "mvsp-b"):
        assert (dev / "key" / f"{name}.yaml").read_bytes() == (
            DATA / "dev" / "key" / f"{name}.yaml"
        ).read_bytes()


def test_main_stops_with_a_message_when_the_fact_sheet_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev = _copy_of_the_data(tmp_path)
    facts = load_yaml(dev / "facts.yaml", Facts)
    dangling = facts.statements[0].model_copy(update={"id": "dangling", "doc": "nope"})
    dump_yaml(facts.model_copy(update={"statements": (*facts.statements, dangling)}), dev / "facts.yaml")
    monkeypatch.setattr(derive_key, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as stopped:  # not the StopIteration of Facts.doc("nope")
        derive_key.main("dev")
    assert stopped.value.code == "fact sheet invalid: run python -m datakit.validate facts"
    assert not (dev / "key").exists()  # nothing derived from a broken sheet was written


def _doc(doc_id: str, **kw: object) -> DocSpec:
    spec = {"id": doc_id, "filename": f"{doc_id}.md", "format": "md", "kind": "policy", **kw}
    return DocSpec.model_validate(spec)


# a, b: no scope; i, i2: the same scope; c: another scope; d, d2: drafts; x: not evidence (template, contract)
RULE_DOCS = (
    _doc("a"),
    _doc("b"),
    _doc("i", scope="internal-systems"),
    _doc("i2", scope="internal-systems"),
    _doc("c", scope="customer-product"),
    _doc("d", status="draft"),
    _doc("d2", status="draft"),
    _doc("x", evidence_allowed=False),
)
# Two date/disagree traps over s0 and s1, the id that sorts last listed first. Every conflict row below puts
# s0 and s1 in conflict, so each pins that the first trap in fact-sheet order labels it: not the first by id,
# not the last. Every other row pins that no trap is attached without a conflict.
RULE_TRAPS = (
    Trap(id="Z9", kind="disagree", statements=("s0", "s1"), note="Listed first."),
    Trap(id="A1", kind="date", statements=("s0", "s1"), note="Listed second, sorts first."),
)
# (document, stance[, flag]) of every statement about one control -> (label, value, scope note expected)
RULES = [
    ([], ("unknown", None, False)),
    ([("x", "yes")], ("unknown", None, False)),
    ([("a", "yes"), ("b", "yes")], ("verified", "Yes", False)),
    ([("a", "no")], ("verified", "No", False)),
    ([("a", "partial")], ("partial", "Partial", False)),
    ([("a", "yes"), ("b", "partial")], ("partial", "Partial", False)),
    ([("a", "no"), ("b", "partial")], ("partial", "Partial", False)),
    ([("i", "yes"), ("c", "no")], ("partial", "Partial", True)),  # both sides declare different scopes
    ([("i", "yes"), ("i2", "no")], ("conflict", None, False)),  # the same scope
    ([("i", "yes"), ("a", "no")], ("conflict", None, False)),  # one side declares none
    ([("a", "yes"), ("b", "no")], ("conflict", None, False)),  # neither declares one
    ([("a", "yes"), ("b", "no"), ("c", "partial")], ("conflict", None, False)),
    ([("d", "yes")], ("partial", "Partial", False)),  # the draft ceiling
    ([("d", "no")], ("partial", "Partial", False)),
    ([("d", "yes"), ("a", "yes")], ("verified", "Yes", False)),  # only when every candidate is in a draft
    ([("d", "yes"), ("a", "no")], ("conflict", None, False)),  # and it does not touch a conflict
    ([("d", "yes"), ("d2", "no")], ("conflict", None, False)),  # not even when every document is a draft
    # an undeclared partial document does not undo the scope partial: only yes and no documents vote
    ([("i", "yes"), ("c", "no"), ("a", "partial")], ("partial", "Partial", True)),
    ([("a", "yes", "injection")], ("unknown", None, False)),  # an injection is never evidence
    ([("a", "yes"), ("b", "no", "injection")], ("verified", "Yes", False)),  # nor one side of a conflict
]


@pytest.mark.parametrize(("statements", "expected"), RULES)
def test_the_decision_rules(
    statements: list[tuple[str, ...]], expected: tuple[str, str | None, bool]
) -> None:
    facts = _facts().model_copy(
        update={
            "documents": RULE_DOCS,
            "traps": RULE_TRAPS,
            "statements": tuple(
                Statement.model_validate(
                    {
                        "id": f"s{n}",
                        "doc": doc,
                        "text": f"Sentence {n}.",
                        "control": "c",
                        "stance": stance,
                        "flags": flags,
                    }
                )
                for n, (doc, stance, *flags) in enumerate(statements)
            ),
        }
    )
    item = SelectionItem(code="Q1", section="S", question="Q?", source="mvsp:1.1", csf_id=None, control="c")
    got = derive_item(facts, item, Selection(questionnaire="t", title="T", buyer="B", items=(item,)))
    assert (got.expected_label, got.expected_value, got.scope_note_expected) == expected
    assert got.must_ask is (expected[0] == "unknown")
    # the first trap in sheet order labels a conflict (see RULE_TRAPS), never the first by id
    assert got.conflict_trap == ("Z9" if expected[0] == "conflict" else None)


@pytest.fixture
def pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the dev pack (fact sheet, documents, keys) that the keys stage reads instead of data/."""
    root = tmp_path / "data" / "dev"
    shutil.copytree(DATA / "dev", root, ignore=shutil.ignore_patterns("src"))
    monkeypatch.setattr(validate, "DATA", tmp_path / "data")
    return root


def test_the_keys_stage_passes_on_the_dev_pack() -> None:
    assert STAGES["keys"]("dev") == []


def test_the_keys_stage_flags_a_missing_and_a_stale_key(pack: Path) -> None:
    (pack / "key" / "vsq-a.yaml").unlink()
    stale = pack / "key" / "mvsp-b.yaml"
    stale.write_text(stale.read_text().replace("expected_label: verified", "expected_label: partial", 1))
    assert STAGES["keys"]("dev") == [
        "key vsq-a is stale: run python -m datakit.derive_key dev",
        "key mvsp-b is stale: run python -m datakit.derive_key dev",
    ]


def test_the_keys_stage_flags_evidence_missing_from_its_document(pack: Path) -> None:
    (pack / "docs" / "data-classification-policy.md").write_text("Nothing is stated here.\n")
    # a missing file: the docs stage says so, and this stage still must not confirm the quote
    (pack / "docs" / "cryptography-policy.docx").unlink()
    found = STAGES["keys"]("dev")
    assert "vsq-a VSQ-22: evidence not found in data-classification-policy.md" in found
    assert "vsq-a VSQ-17: evidence not found in cryptography-policy.docx" in found
    assert not [p for p in found if "VSQ-01:" in p]


def test_the_keys_stage_flags_an_unplanned_conflict_and_an_unexercised_trap(pack: Path) -> None:
    facts = load_yaml(pack / "facts.yaml", Facts)
    spare = Trap(id="Z1", kind="must_ask", note="Nothing asks about this.")
    # D3, not a disagree trap: the sheet must stay valid (minimum trap counts) or the stage stops early
    changed = facts.model_copy(update={"traps": (*(t for t in facts.traps if t.id != "D3"), spare)})
    dump_yaml(changed, pack / "facts.yaml")
    for name in ("vsq-a", "mvsp-b"):
        dump_yaml(derive(changed, _selection(name)), pack / "key" / f"{name}.yaml")
    assert STAGES["keys"]("dev") == [
        "vsq-a VSQ-22: conflict without a planted trap (unplanned contradiction?)",
        "trap Z1 is not exercised by any vsq-a item",
    ]


def test_the_keys_stage_points_to_the_facts_stage_when_the_sheet_is_invalid(pack: Path) -> None:
    facts = load_yaml(pack / "facts.yaml", Facts)
    dangling = facts.statements[0].model_copy(update={"id": "dangling", "doc": "nope"})
    dump_yaml(facts.model_copy(update={"statements": (*facts.statements, dangling)}), pack / "facts.yaml")
    assert STAGES["keys"]("dev") == ["fact sheet invalid: run python -m datakit.validate facts"]


def test_the_facts_stage_and_the_keys_share_one_evidence_predicate() -> None:
    assert validate.is_usable_evidence is derive_key.is_usable_evidence

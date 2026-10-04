import shutil
from collections import Counter
from pathlib import Path

import pytest

from datakit import validate
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


# the control each conflict trap is planted on
CONFLICTS = {
    "D1": "access-review",
    "D2": "cloud-only",
    "D3": "data-residency",
    "X1": "backup-restore-test",
    "X2": "log-retention",
}


def test_planted_traps_come_out_as_designed() -> None:
    k = _by_control("vsq-a")
    for trap, control in CONFLICTS.items():
        assert all(
            x.expected_label == "conflict" and x.expected_value is None and x.conflict_trap == trap
            for x in k[control]
        ), trap
    assert all(x.expected_label == "partial" and x.scope_note_expected for x in k["mfa"])
    assert all(x.expected_label == "partial" and x.scope_note_expected for x in k["background-checks"])
    for c in ("iso27001", "ml-training", "bug-bounty", "dast", "customer-pentest"):
        assert all(
            x.expected_label == "verified" and x.expected_value == "No" and x.honest_negative for x in k[c]
        ), c
    for c in ("laptop-encryption", "ir-plan"):
        assert all(x.expected_label == "partial" for x in k[c]), c
    must_ask = [c for t in _facts().traps if t.kind == "must_ask" for c in t.controls]
    assert len(must_ask) == 13
    for c in must_ask:
        assert all(x.expected_label == "unknown" and x.must_ask for x in k[c]), c
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


def _doc(doc_id: str, **kw: object) -> DocSpec:
    spec = {"id": doc_id, "filename": f"{doc_id}.md", "format": "md", "kind": "policy", **kw}
    return DocSpec.model_validate(spec)


# a, b: no scope; i, i2: the same scope; c: another scope; d: a draft; x: not evidence (template, contract)
RULE_DOCS = (
    _doc("a"),
    _doc("b"),
    _doc("i", scope="internal-systems"),
    _doc("i2", scope="internal-systems"),
    _doc("c", scope="customer-product"),
    _doc("d", status="draft"),
    _doc("x", evidence_allowed=False),
)
# (document, stance) of every statement about one control -> (label, value, scope note expected)
RULES = [
    ([], ("unknown", None, False)),
    ([("x", "yes")], ("unknown", None, False)),
    ([("a", "yes"), ("b", "yes")], ("verified", "Yes", False)),
    ([("a", "no")], ("verified", "No", False)),
    ([("a", "partial")], ("partial", "Partial", False)),
    ([("a", "yes"), ("b", "partial")], ("partial", "Partial", False)),
    ([("a", "no"), ("b", "partial")], ("partial", "Partial", False)),
    (
        [("i", "yes"), ("c", "no")],
        ("partial", "Partial", True),
    ),  # both sides declare a scope and the scopes differ
    ([("i", "yes"), ("i2", "no")], ("conflict", None, False)),  # the same scope
    ([("i", "yes"), ("a", "no")], ("conflict", None, False)),  # one side declares none
    ([("a", "yes"), ("b", "no"), ("c", "partial")], ("conflict", None, False)),
    ([("d", "yes")], ("partial", "Partial", False)),  # the draft ceiling
    ([("d", "no")], ("partial", "Partial", False)),
    ([("d", "yes"), ("a", "yes")], ("verified", "Yes", False)),  # only when every candidate is in a draft
    ([("d", "yes"), ("a", "no")], ("conflict", None, False)),  # and it does not touch a conflict
]


@pytest.mark.parametrize(("statements", "expected"), RULES)
def test_the_decision_rules(
    statements: list[tuple[str, str]], expected: tuple[str, str | None, bool]
) -> None:
    facts = _facts().model_copy(
        update={
            "documents": RULE_DOCS,
            "traps": (),
            "statements": tuple(
                Statement.model_validate(
                    {"id": f"s{n}", "doc": doc, "text": f"Sentence {n}.", "control": "c", "stance": stance}
                )
                for n, (doc, stance) in enumerate(statements)
            ),
        }
    )
    item = SelectionItem(code="Q1", section="S", question="Q?", source="mvsp:1.1", csf_id=None, control="c")
    got = derive_item(facts, item, Selection(questionnaire="t", title="T", buyer="B", items=(item,)))
    assert (got.expected_label, got.expected_value, got.scope_note_expected) == expected
    assert got.must_ask is (expected[0] == "unknown")


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
    changed = facts.model_copy(update={"traps": (*(t for t in facts.traps if t.id != "X2"), spare)})
    dump_yaml(changed, pack / "facts.yaml")
    for name in ("vsq-a", "mvsp-b"):
        dump_yaml(derive(changed, _selection(name)), pack / "key" / f"{name}.yaml")
    assert STAGES["keys"]("dev") == [
        "vsq-a VSQ-53: conflict without a planted trap (unplanned contradiction?)",
        "trap Z1 is not exercised by any vsq-a item",
    ]

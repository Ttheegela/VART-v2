"""Derive the expected answer for every questionnaire item from the fact sheet (spec section 6.7 rules), so
the key is consistent with the documents by construction.   python -m datakit.derive_key dev"""

import sys
from pathlib import Path

from datakit.schemas import (
    Facts,
    Key,
    KeyEvidence,
    KeyItem,
    Label,
    Selection,
    SelectionItem,
    Statement,
    Value,
    dump_yaml,
    load_yaml,
)

ROOT = Path(__file__).resolve().parent.parent


def is_usable_evidence(f: Facts, s: Statement) -> bool:
    """The one rule for what can back an answer; the keys and the facts stage (validate.py) both use it."""
    return f.doc(s.doc).evidence_allowed and not {"placeholder", "injection"} & set(s.flags)


def _candidates(f: Facts, control: str) -> list[Statement]:
    return [s for s in f.statements_for(control) if is_usable_evidence(f, s)]


def derive_item(f: Facts, item: SelectionItem, sel: Selection) -> KeyItem:
    cands = _candidates(f, item.control)
    stances = {s.stance for s in cands}
    label: Label = "unknown"
    value: Value | None = None
    scope_note = False
    conflict_trap: str | None = None
    if cands:
        if {"yes", "no"} <= stances:
            yes_scopes = {f.doc(s.doc).scope for s in cands if s.stance == "yes"}
            no_scopes = {f.doc(s.doc).scope for s in cands if s.stance == "no"}
            if None not in yes_scopes | no_scopes and yes_scopes.isdisjoint(no_scopes):
                label, value, scope_note = "partial", "Partial", True
            else:
                label = "conflict"
                ids = {s.id for s in cands}
                conflict_trap = next(
                    (t.id for t in f.traps if t.kind in ("date", "disagree") and ids & set(t.statements)),
                    None,
                )
        elif stances == {"yes"}:
            label, value = "verified", "Yes"
        elif stances == {"no"}:
            label, value = "verified", "No"
        else:
            label, value = "partial", "Partial"
        if label == "verified" and all(f.doc(s.doc).status == "draft" for s in cands):
            label, value = "partial", "Partial"
    about = {s.id for s in f.statements_for(item.control)}
    traps = tuple(sorted(t.id for t in f.traps if about & set(t.statements) or item.control in t.controls))
    filled = {
        c for t in f.traps if t.kind == "fills" and t.controls[0] == item.control for c in t.controls[1:]
    }
    honest = any(t.kind == "honest_negative" and about & set(t.statements) for t in f.traps)
    return KeyItem(
        code=item.code,
        expected_label=label,
        expected_value=value,
        must_ask=not cands,
        evidence=tuple(KeyEvidence(doc=s.doc, quote=s.text, stance=s.stance) for s in cands),
        conflict_trap=conflict_trap,
        scope_note_expected=scope_note,
        honest_negative=honest,
        traps=traps,
        fills=tuple(i.code for i in sel.items if i.control in filled),
    )


def derive(f: Facts, sel: Selection) -> Key:
    return Key(
        pack=f.pack, questionnaire=sel.questionnaire, items=tuple(derive_item(f, i, sel) for i in sel.items)
    )


def main(pack: str) -> None:
    from datakit.validate import check_facts  # validate imports this module, so it cannot be imported above

    facts = load_yaml(ROOT / "data" / pack / "facts.yaml", Facts)
    if check_facts(facts):  # a dangling reference would otherwise end in a StopIteration traceback
        raise SystemExit("fact sheet invalid: run python -m datakit.validate facts")
    for name in ("vsq-a", "mvsp-b"):
        sel = load_yaml(ROOT / "data" / "questionnaires" / f"{name}.selection.yaml", Selection)
        dump_yaml(derive(facts, sel), ROOT / "data" / pack / "key" / f"{name}.yaml")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")

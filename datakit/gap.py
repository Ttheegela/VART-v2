"""The CSF gap-check answer key (CSF spec 8). data/<pack>/gap/facts.yaml extends the pack's fact sheet
with what only the gap check uses (documents, controls, statements, traps) and maps each Checked CSF
outcome to the one control that answers it. The key comes from derive_key's rules over the merged sheet, so
it agrees with the documents by construction: nobody writes an answer to match the engine.
python -m datakit.gap dev"""

import sys
from collections import Counter
from pathlib import Path

from app.csf import Outcome, framework, gap_label
from app.text import contains
from datakit.derive_key import derive, is_usable_evidence
from datakit.extract import lines_of
from datakit.schemas import DocSpec, Facts, GapFacts, Key, Selection, SelectionItem, dump_yaml, load_yaml

ROOT = Path(__file__).resolve().parent.parent
NAME = "csf-core"
# CSF spec 8. An honest gap: no statement at all speaks to its control (a template-only Gap is a trap).
MIN_PLANTED = {"documents_disagree": 2, "not_met": 2, "honest gap": 2}
TRAP_SOURCES = ("template", "draft", "planned")


def gap_dir(pack: str) -> Path:
    return ROOT / "data" / pack / "gap"


def load(pack: str) -> tuple[Facts, GapFacts]:
    return (
        load_yaml(ROOT / "data" / pack / "facts.yaml", Facts),
        load_yaml(gap_dir(pack) / "facts.yaml", GapFacts),
    )


def merged(facts: Facts, gap: GapFacts) -> Facts:
    data = facts.model_dump()
    extra = gap.model_dump()
    for field in ("documents", "controls", "statements", "traps"):
        data[field] = [*data[field], *extra[field]]
    return Facts.model_validate(data)


def checked() -> list[Outcome]:
    return [o for o in framework().outcomes if o.tier == "checked"]


def selection(facts: Facts, gap: GapFacts) -> Selection:
    control = {m.csf_id: m.control for m in gap.outcomes}
    return Selection(
        questionnaire=NAME,
        title="NIST CSF 2.0 core",
        buyer=facts.buyer,
        items=tuple(
            SelectionItem(
                code=o.id,
                section=o.category,
                question=o.question or "",
                source=f"csf:{o.id}",
                csf_id=o.id,
                control=control[o.id],
            )
            for o in checked()
        ),
    )


def derive_gap(facts: Facts, gap: GapFacts) -> Key:
    key = derive(merged(facts, gap), selection(facts, gap))
    partly = {m.csf_id for m in gap.outcomes if m.label == "partly_covered"}
    items = tuple(
        k.model_copy(update={"expected_label": "partial", "expected_value": "Partial"})
        if k.code in partly
        else k
        for k in key.items
    )
    return key.model_copy(update={"items": items})


def doc_path(pack: str, gap: GapFacts, spec: DocSpec) -> Path:
    base = gap_dir(pack) if spec.id in {d.id for d in gap.documents} else ROOT / "data" / pack
    return base / "docs" / spec.filename


def trap_sources(f: Facts, control: str) -> set[str]:
    """Why an outcome is a trap (CSF spec 8): every statement about its control is in a template (or has a
    placeholder), in a draft, or only planned. Empty when any final, usable statement speaks to it."""
    planned = {s for t in f.traps if t.kind == "planned_only" for s in t.statements}
    out: set[str] = set()
    for s in f.statements_for(control):
        doc = f.doc(s.doc)
        if not doc.evidence_allowed or "placeholder" in s.flags:
            out.add("template")
        elif doc.status == "draft":
            out.add("draft")
        elif s.id in planned:
            out.add("planned")
        else:
            return set()
    return out


def check(pack: str) -> list[str]:
    from datakit.validate import check_facts  # validate imports this module

    facts, gap = load(pack)
    f = merged(facts, gap)
    if p := check_facts(f):
        return p
    ids = [m.csf_id for m in gap.outcomes]
    want = {o.id for o in checked()}
    controls = {c.id for c in f.controls}
    p += [f"outcome {i} is mapped twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    p += [
        f"outcome {m.csf_id}: a label override needs missing"
        for m in gap.outcomes
        if m.label and not (m.missing or "").strip()
    ]
    count = {o.id: len(o.parts) for o in checked()}
    p += [
        f"outcome {m.csf_id}: a label override needs missing_parts"
        for m in gap.outcomes
        if m.label and not m.missing_parts
    ]
    p += [
        f"outcome {m.csf_id}: missing_parts without a label override"
        for m in gap.outcomes
        if m.missing_parts and not m.label
    ]
    p += [
        f"outcome {m.csf_id}: no part {n}"
        for m in gap.outcomes
        for n in m.missing_parts
        if not 1 <= n <= count.get(m.csf_id, 0)
    ]
    p += [f"Checked outcome {i} has no control" for i in sorted(want - set(ids))]
    p += [f"outcome {i} is not a Checked CSF outcome" for i in sorted(set(ids) - want)]
    p += [
        f"outcome {m.csf_id}: unknown control {m.control}" for m in gap.outcomes if m.control not in controls
    ]
    if p:
        return p
    lines = {d.id: lines_of(doc_path(pack, gap, d)) for d in f.documents}
    p += [
        f"statement {s.id} not found verbatim in {f.doc(s.doc).filename}"
        for s in gap.statements
        if not any(contains(line, s.text) for line in lines[s.doc])
    ]
    p += [
        f"{d.filename} is not ASCII"
        for d in gap.documents
        if not doc_path(pack, gap, d).read_bytes().isascii()
    ]
    key = derive_gap(facts, gap)
    path = ROOT / "data" / pack / "key" / f"{NAME}.yaml"
    if not path.exists() or load_yaml(path, Key) != key:
        p.append(f"key {NAME} is stale: run python -m datakit.gap {pack}")
    p += [
        f"{k.code}: evidence not found in {f.doc(e.doc).filename}"
        for k in key.items
        for e in k.evidence
        if not any(contains(line, e.quote) for line in lines[e.doc])
    ]
    p += [
        f"{k.code}: conflict without a planted trap"
        for k in key.items
        if k.expected_label == "conflict" and k.conflict_trap is None
    ]
    control = {m.csf_id: m.control for m in gap.outcomes}
    # A CSF part states no threshold (spec 4), so a planted disagreement must rest on a no the part can see: a
    # negated sentence or a record row's status, not a longer interval (spec 10, adversary C1).
    p += [
        f"{k.code}: conflict {k.conflict_trap} rests on a thresholded no the CSF part cannot see"
        for k in key.items
        if k.expected_label == "conflict"
        and not all(
            "negation" in s.flags or "Status: " in s.text
            for s in f.statements_for(control[k.code])
            if s.stance == "no" and is_usable_evidence(f, s)
        )
    ]
    labels = {
        k.code: gap_label(framework().get(k.code), k.expected_label, k.expected_value) for k in key.items
    }
    planted: Counter[str | None] = Counter(labels.values())
    planted["honest gap"] = sum(x == "gap" and not f.statements_for(control[c]) for c, x in labels.items())
    p += [
        f"only {planted[x]} {x} outcome(s) planted, need {n}"
        for x, n in MIN_PLANTED.items()
        if planted[x] < n
    ]
    found = set().union(*(trap_sources(f, control[k.code]) for k in key.items))
    p += [f"no trap outcome where only a {s} source speaks" for s in TRAP_SOURCES if s not in found]
    return p


def main(pack: str) -> None:
    facts, gap = load(pack)
    dump_yaml(derive_gap(facts, gap), ROOT / "data" / pack / "key" / f"{NAME}.yaml")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")

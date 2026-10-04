"""Mechanical checks over data/. CI runs `python -m datakit.validate all`.

python -m datakit.validate facts|docs|questionnaires|keys|mapper|all [--pack dev]
"""

import argparse
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

from datakit.questionnaires import OUT as QDIR
from datakit.questionnaires import build_csv, build_xlsx, mvsp_items, vsaq_items
from datakit.schemas import Facts, Selection, TrapKind, load_yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

Check = Callable[[str], list[str]]
STAGES: dict[str, Check] = {}


def stage(name: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        STAGES[name] = fn
        return fn

    return register


MIN_TRAPS: dict[TrapKind, int] = {
    "date": 2,
    "disagree": 2,
    "scope": 2,
    "negation": 3,
    "honest_negative": 5,
    "placeholder": 2,
    "draft_only": 2,
    "injection": 2,
    "must_ask": 5,
    "fills": 2,
}


def _dupes(values: list[str]) -> list[str]:
    return sorted({v for v in values if values.count(v) > 1})


def check_facts(f: Facts) -> list[str]:
    p: list[str] = []
    for what, ids in (
        ("document", [d.id for d in f.documents]),
        ("filename", [d.filename for d in f.documents]),
        ("control", [c.id for c in f.controls]),
        ("statement", [s.id for s in f.statements]),
        ("trap", [t.id for t in f.traps]),
    ):
        p += [f"duplicate {what} id {d}" for d in _dupes(ids)]
    docs = {d.id for d in f.documents}
    controls = {c.id for c in f.controls}
    stmts = {s.id: s for s in f.statements}
    for s in f.statements:
        if s.doc not in docs:
            p.append(f"statement {s.id}: unknown doc {s.doc}")
        if s.control is None and "injection" not in s.flags:
            p.append(f"statement {s.id}: only injections may have no control")
        if s.control is not None and s.control not in controls:
            p.append(f"statement {s.id}: unknown control {s.control}")
        if not s.text.isascii():
            p.append(f"statement {s.id}: text must be ASCII")
    if any(p):
        return p  # the checks below assume references resolve

    def evidence(control: str) -> list[str]:
        return [
            s.id
            for s in f.statements_for(control)
            if f.doc(s.doc).evidence_allowed and not {"placeholder", "injection"} & set(s.flags)
        ]

    for t in f.traps:
        ss = [stmts[i] for i in t.statements if i in stmts]
        p += [f"trap {t.id}: unknown statement {i}" for i in t.statements if i not in stmts]
        p += [f"trap {t.id}: unknown control {c}" for c in t.controls if c not in controls]
        stances = {s.stance for s in ss}
        scopes = [f.doc(s.doc).scope for s in ss]
        if t.kind in ("date", "disagree", "scope") and not (
            {"yes", "no"} <= stances and len({s.doc for s in ss}) >= 2 and len({s.control for s in ss}) == 1
        ):
            p.append(f"trap {t.id}: needs yes and no from two documents about one control")
        if t.kind == "date":
            records = [s for s in ss if f.doc(s.doc).kind == "record"]
            others = [s for s in ss if f.doc(s.doc).kind != "record"]
            if (
                not records
                or not others
                or not all(
                    (f.doc(r.doc).dated or date.min) > (f.doc(o.doc).dated or date.max)
                    for r in records
                    for o in others
                )
            ):
                p.append(f"trap {t.id}: a record must be dated after the documents it contradicts")
        if t.kind == "disagree" and len({sc for sc in scopes if sc}) > 1:
            p.append(f"trap {t.id}: documents with two different scopes are a scope trap, not a disagreement")
        if t.kind == "scope" and (None in scopes or len(set(scopes)) < 2):
            p.append(f"trap {t.id}: both documents need different declared scopes")
        if t.kind == "negation" and not all("negation" in s.flags and s.stance == "no" for s in ss):
            p.append(f"trap {t.id}: negation statements must be flagged negation with stance no")
        if t.kind == "honest_negative":
            for s in ss:
                ev = evidence(s.control or "")
                if not ev or any(stmts[i].stance != "no" for i in ev):
                    p.append(f"trap {t.id}: every usable statement about {s.control} must say no")
        if t.kind == "placeholder" and not all("placeholder" in s.flags and "[" in s.text for s in ss):
            p.append(f"trap {t.id}: placeholder statements need the flag and a [bracketed] placeholder")
        if t.kind == "draft_only":
            for s in ss:
                if any(f.doc(stmts[i].doc).status != "draft" for i in evidence(s.control or "")):
                    p.append(f"trap {t.id}: {s.control} must have draft-only evidence")
        if t.kind == "injection" and not all("injection" in s.flags and s.control is None for s in ss):
            p.append(f"trap {t.id}: injection statements need the flag and no control")
        if t.kind == "injection" and not t.controls:
            p.append(f"trap {t.id}: list the controls the injection tries to sway")
        if t.kind == "must_ask":
            p += [f"trap {t.id}: {c} has usable evidence" for c in t.controls if evidence(c)]
        if t.kind == "fills" and len(t.controls) < 2:
            p.append(f"trap {t.id}: fills needs an answered control and at least one filled control")
    kinds = [t.kind for t in f.traps]
    p += [f"only {kinds.count(k)} {k} trap(s), need {n}" for k, n in MIN_TRAPS.items() if kinds.count(k) < n]
    return p


@stage("facts")
def _facts_stage(pack: str) -> list[str]:
    return check_facts(load_yaml(DATA / pack / "facts.yaml", Facts))


@stage("questionnaires")
def _questionnaires_stage(pack: str) -> list[str]:
    p: list[str] = []
    known = vsaq_items() | mvsp_items()
    controls = {c.id for c in load_yaml(DATA / pack / "facts.yaml", Facts).controls}
    for name, builder, suffix in (("vsq-a", build_xlsx, "xlsx"), ("mvsp-b", build_csv, "csv")):
        sel = load_yaml(QDIR / f"{name}.selection.yaml", Selection)
        p += [f"{name} {i.code}: unknown source {i.source}" for i in sel.items if i.source not in known]
        p += [f"{name} {i.code}: unknown control {i.control}" for i in sel.items if i.control not in controls]
        p += [f"{name} {i.code}: question must be ASCII" for i in sel.items if not i.question.isascii()]
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / f"{name}.{suffix}"
            builder(sel, fresh)
            if fresh.read_bytes() != (QDIR / f"{name}.{suffix}").read_bytes():
                p.append(f"{name}.{suffix} is stale: run python -m datakit.questionnaires")
    covered = {i.control for i in load_yaml(QDIR / "vsq-a.selection.yaml", Selection).items}
    p += [f"vsq-a never asks about control {c}" for c in sorted(controls - covered)]
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=[*STAGES, "all"])
    ap.add_argument("--pack", default="dev")
    args = ap.parse_args(argv)
    names = list(STAGES) if args.stage == "all" else [args.stage]
    problems = [f"{name}: {p}" for name in names for p in STAGES[name](args.pack)]
    for p in problems:
        print(p, file=sys.stderr)
    print(f"datakit.validate {args.stage}: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

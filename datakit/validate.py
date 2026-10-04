"""Mechanical checks over data/. CI runs `python -m datakit.validate all`.

python -m datakit.validate facts|docs|questionnaires|keys|mapper|all [--pack dev]
"""

import argparse
import re
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

from app.text import contains
from datakit.derive_key import derive, is_usable_evidence
from datakit.extract import lines_of
from datakit.mapper_variants import build_all
from datakit.questionnaires import OUT as QDIR
from datakit.questionnaires import build_csv, build_xlsx, mapping_json, mvsp_items, vsaq_items
from datakit.render import render_pack
from datakit.schemas import Facts, Key, Selection, TrapKind, load_yaml

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


# The net for "this line speaks to a control". tests/datakit/test_render.py fails on a rendered line
# (for a PDF: a sentence) that CONTROL_WORDS finds and that is neither inside a registered statement nor
# listed in data/dev/src/ALLOWED_LINES.txt. A stem matches at a word start with any ending ("review"
# finds "reviewed" but not "preview"), also after "un" or "non" ("unencrypted"), and its words may be
# joined by a space or a hyphen ("bug bounty" finds "bug-bounty"). An acronym matches only as a whole
# word, singular or plural ("NDAs"; "sla" is not inside "islands", "sso" not inside "association", "nda"
# not inside "agenda"); "\w@" finds an email address or a mailbox name. The first group of stems is topics
# with registered statements; the others are topics no document may speak to (the must-ask controls).
# There is no bare "training" stem: that is the documented awareness training.
CONTROL_STEMS = (
    "review",
    "multi-factor",
    "encrypt",
    "backup",
    "retain",
    "retention",
    "penetration",
    "background check",
    "on-premises",
    "bug bounty",
    "tabletop",
    "notify",
    # must-ask, from the MVSP short form
    "self-assessment",
    "mvsp",
    "data flow",
    "dataflow",
    "diagram",
    "security header",
    "response header",
    "content security policy",
    "x-frame-options",
    "hsts",
    "physical access",
    "badge",
    "visitor",
    "reception",
    "key card",
    "keycard",
    "fob",
    "single sign-on",
    "saml",
    "oidc",
    "federat",
    "identity provider",
    "secure coding",
    "developer security training",
    "developer training",
    "train your developers",
    "trained",
    # must-ask, about the engagement
    "insurance",
    "cyber",
    "coverage",
    "cmek",
    "byok",
    "customer-managed",
    "bring your own",
    "uptime",
    "service level",
    "99.9",
    "security contact",
    "incident contact",
    "24/7",
    "report sharing",
    "non-disclosure",
    "distribute",
)
CONTROL_ACRONYMS = ("mfa", "dast", "sso", "nda", "sla", "csp")


def _stem_pattern(stem: str) -> str:
    words = "[ -]".join(re.escape(word) for word in re.split(r"[ -]", stem))
    return rf"\b(?:un|non)?{words}\w*"


CONTROL_WORDS = re.compile(
    "|".join(
        [
            *map(_stem_pattern, CONTROL_STEMS),
            *(rf"\b{acronym}s?\b" for acronym in CONTROL_ACRONYMS),
            r"\w@",
        ]
    ),
    re.IGNORECASE,
)


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
        if "negation" in s.flags and s.stance == "yes":
            p.append(f"statement {s.id}: a statement flagged negation cannot have stance yes")
    if any(p):
        return p  # the checks below assume references resolve

    def evidence(control: str) -> list[str]:
        return [s.id for s in f.statements_for(control) if is_usable_evidence(f, s)]

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
    if (QDIR / "vsq-a.mapping.json").read_bytes() != mapping_json().encode("utf-8"):
        p.append("vsq-a.mapping.json is stale: run python -m datakit.questionnaires")
    covered = {i.control for i in load_yaml(QDIR / "vsq-a.selection.yaml", Selection).items}
    p += [f"vsq-a never asks about control {c}" for c in sorted(controls - covered)]
    return p


@stage("docs")
def _docs_stage(pack: str) -> list[str]:
    p: list[str] = []
    base = DATA / pack
    facts = load_yaml(base / "facts.yaml", Facts)
    lines = {
        d.id: lines_of(base / "docs" / d.filename)
        for d in facts.documents
        if (base / "docs" / d.filename).exists()
    }
    p += [f"missing rendered file {d.filename}" for d in facts.documents if d.id not in lines]
    for s in facts.statements:
        # a PDF reads back as one joined line (wrapping is not a paragraph break), so this covers PDFs too
        if s.doc in lines and not any(contains(line, s.text) for line in lines[s.doc]):
            p.append(f"statement {s.id} not found verbatim in {facts.doc(s.doc).filename}")
    p += [
        f"{src.name} is not ASCII"
        for src in sorted((base / "src").glob("*"))
        if not src.read_bytes().isascii()
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for fresh in render_pack(pack, Path(tmp)):
            kept = base / "docs" / fresh.name
            if kept.exists() and fresh.read_bytes() != kept.read_bytes():
                p.append(f"{fresh.name} is stale: run python -m datakit.render {pack}")
    return p


@stage("keys")
def _keys_stage(pack: str) -> list[str]:
    p: list[str] = []
    base = DATA / pack
    facts = load_yaml(base / "facts.yaml", Facts)
    if check_facts(facts):
        return ["fact sheet invalid: run python -m datakit.validate facts"]
    lines = {
        d.id: lines_of(base / "docs" / d.filename)
        for d in facts.documents
        if (base / "docs" / d.filename).exists()
    }
    keys: dict[str, Key] = {}
    for name in ("vsq-a", "mvsp-b"):
        sel = load_yaml(QDIR / f"{name}.selection.yaml", Selection)
        path = base / "key" / f"{name}.yaml"
        key = load_yaml(path, Key) if path.exists() else None
        if key is None or key != derive(facts, sel):
            p.append(f"key {name} is stale: run python -m datakit.derive_key {pack}")
            continue
        keys[name] = key
        # a PDF reads back as one joined line (wrapping is not a paragraph break), so this covers PDFs too
        p += [
            f"{name} {item.code}: evidence not found in {facts.doc(ev.doc).filename}"
            for item in key.items
            for ev in item.evidence
            if not any(contains(line, ev.quote) for line in lines.get(ev.doc, []))
        ]
        p += [
            f"{name} {item.code}: conflict without a planted trap (unplanned contradiction?)"
            for item in key.items
            if item.expected_label == "conflict" and item.conflict_trap is None
        ]
    if "vsq-a" in keys:
        exercised = {t for item in keys["vsq-a"].items for t in item.traps}
        p += [f"trap {t.id} is not exercised by any vsq-a item" for t in facts.traps if t.id not in exercised]
    return p


@stage("mapper")
def _mapper_stage(pack: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        expected = build_all(fresh)

        def stale(name: str) -> bool:
            kept = DATA / "mapper" / name
            return not kept.exists() or kept.read_bytes() != (fresh / name).read_bytes()

        p = [
            f"mapper/{name} is stale: run python -m datakit.mapper_variants"
            for name in expected
            if stale(name)
        ]
        if stale("expected.json"):
            p.append("mapper/expected.json is stale")
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

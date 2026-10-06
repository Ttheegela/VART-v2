"""NIST CSF 2.0 reference data for the gap check (CSF spec 4). NIST's part (ids, function and category
names, outcome text, SP 800-53 Rev 5.2.0 references) comes only from the committed extract of NIST's CSF 2.0
Reference Tool export; VART's part (tier, question, parts) only from data/csf/tiers.yaml. The app reads the
built file and never fetches anything.

    python -m datakit.csf extract DOWNLOAD.xlsx --retrieved YYYY-MM-DD   # the lead, once per NIST refresh
    python -m datakit.csf build                                         # writes data/csf/csf-2.0.json
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl

from datakit.schemas import load_yaml_raw

ROOT = Path(__file__).resolve().parent.parent
CSF = ROOT / "data" / "csf"
EXTRACT = CSF / "source" / "csf-2.0-extract.json"
TIERS = CSF / "tiers.yaml"
BUILT = CSF / "csf-2.0.json"
DOWNLOAD_URL = "https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all"
TOOL_URL = "https://csrc.nist.gov/projects/cybersecurity-framework/filters#/csf/filters"
SHEET = "CSF 2.0"
REFERENCE = "SP 800-53 Rev 5.2.0: "
OUTCOMES = 106
# A control (AC-02), an enhancement (CP-02(08)) or, where NIST maps a whole family, the family (PT).
CONTROL = re.compile(r"[A-Z]{2}(?:-\d{2}(?:\(\d{2}\))?)?")
_CODE = re.compile(r"\(([A-Z]{2}(?:\.[A-Z]{2})?)\)")
_OUTCOME = re.compile(r"([A-Z]{2}\.[A-Z]{2}-\d{2}): (.+)", re.DOTALL)
NIST_FIELDS = ("id", "function", "category", "outcome", "related_controls", "source_url")
# Question words a part may use besides NIST's own (CSF spec 4, amended): none names a thing or a requirement.
_FRAME_WORDS = "a an the is are do does its their of and to for in by from as such example through"
FRAME = frozenset(_FRAME_WORDS.split())
MAX_PARAPHRASE = 3  # words per outcome (adversary checkpoint 2, I3)
_WORD = re.compile(r"[a-z]+")
_EXAMPLE = re.compile(r"\b(?:such as|for example)\b")


def _stem(word: str) -> str:
    """Enough to match NIST's inflections: inventories/inventory, managed/manage, processes/process."""
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)] + ("y" if suffix == "ies" else "")
            break
    return word.removesuffix("e")


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("'s", ""))


def added_words(part: str, nist: str) -> list[str]:
    """The words of a part that are neither question words nor NIST's (compared by stem), in order."""
    have = {_stem(w) for w in words(nist)}
    return [w for w in words(part) if w not in FRAME and _stem(w) not in have]


def _part_problems(i: str, listed: list[Any], mapping: dict[str, Any], outcome: str, nist: str) -> list[str]:
    """Each part is a question in NIST's words for this outcome. Any other word stands in an example clause
    ("such as" or "for example", up to the next comma or the question mark) and is on the outcome's
    paraphrase_words, mapped to the NIST word it is an instance of (at most MAX_PARAPHRASE). Together the
    parts carry every word of NIST's outcome."""
    if not listed:
        return [f"checked {i}: no parts"]
    have = {_stem(w) for w in words(nist)}
    p = [
        f"{i}: paraphrase word {w!r} must map to a word of NIST's text, not {t!r}"
        for w, t in mapping.items()
        if not (isinstance(t, str) and t.lower() not in FRAME and _stem(t.lower()) in have)
    ]
    if len(mapping) > MAX_PARAPHRASE:
        p.append(f"{i}: {len(mapping)} paraphrase words, at most {MAX_PARAPHRASE}")
    for n, q in enumerate(listed, 1):
        if not (isinstance(q, str) and q.isascii() and q.rstrip().endswith("?") and '"' not in q):
            p.append(f"{i} part {n}: must be ASCII, quote nothing and end with '?'")
            continue
        # The example clause runs from "such as" / "for example" to the next comma or the question mark.
        m = _EXAMPLE.search(q.lower())
        in_example = set(words(re.split(r"[,?]", q.lower()[m.end() :])[0])) if m else set()
        for w in added_words(q, nist):
            if w not in mapping:
                p.append(f"{i} part {n}: adds {w!r}, not in NIST's text")
            elif w not in in_example:
                p.append(f"{i} part {n}: {w!r} stands outside an example clause")
    used = [w for q in listed if isinstance(q, str) for w in words(q)]
    stems = {_stem(w) for w in used}
    p += [
        f"{i}: NIST's {w!r} is in no part"
        for w in dict.fromkeys(words(outcome))
        if w not in FRAME and _stem(w) not in stems
    ]
    p += [f"{i}: paraphrase word {w!r} is in no part" for w in sorted(set(mapping) - set(used))]
    return p


def extract(path: Path) -> list[dict[str, Any]]:
    """One entry per active outcome, in NIST's order. Function and category names are read from their own rows
    ("PROTECT (PR): ...", "Data Security (PR.DS): ...") and looked up by code, so row order does not matter;
    withdrawn rows are skipped."""
    sheet = openpyxl.load_workbook(path, read_only=True)[SHEET]
    rows = [tuple(r) + (None,) * 5 for r in sheet.iter_rows(min_row=3, values_only=True)]
    names: dict[str, str] = {}
    for row in rows:
        for cell in row[:2]:
            if isinstance(cell, str) and "[Withdrawn" not in cell and (m := _CODE.search(cell)):
                names[m.group(1)] = cell[: m.start()].strip()
    out: list[dict[str, Any]] = []
    for row in rows:
        cell, refs = row[2], row[4]
        if not isinstance(cell, str) or "[Withdrawn" in cell or not (m := _OUTCOME.fullmatch(cell.strip())):
            continue
        csf_id = m.group(1)
        controls = [
            x[len(REFERENCE) :].strip() for x in str(refs or "").splitlines() if x.startswith(REFERENCE)
        ]
        out.append(
            {
                "id": csf_id,
                "function": names[csf_id[:2]].title(),
                "category": names[csf_id.split("-")[0]],
                "outcome": m.group(2).strip(),
                "related_controls": list(dict.fromkeys(controls)),
            }
        )
    if not any(o["related_controls"] for o in out):
        raise ValueError(
            f"{path.name}: no outcome has a '{REFERENCE.strip()}' reference; did NIST change the export?"
        )
    return out


def extract_file(path: Path, retrieved: str) -> dict[str, Any]:
    return {
        "source": DOWNLOAD_URL,
        "retrieved": retrieved,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "csf_version": "2.0",
        "outcomes": extract(path),
    }


def _tier(tiers: dict[str, Any], csf_id: str) -> str:
    return next((t for t in ("checked", "ask") if csf_id in (tiers.get(t) or {})), "not_checked")


def build(nist: dict[str, Any], tiers: dict[str, Any]) -> dict[str, Any]:
    parts = tiers.get("parts") or {}

    def entry(o: dict[str, Any]) -> dict[str, Any]:
        tier = _tier(tiers, o["id"])
        question = (tiers.get(tier) or {}).get(o["id"]) if tier != "not_checked" else None
        listed = list(parts.get(o["id"]) or []) if tier == "checked" else []
        return {**o, "source_url": TOOL_URL, "tier": tier, "question": question, "parts": listed}

    return {
        "csf_version": nist["csf_version"],
        "retrieved": nist["retrieved"],
        "source": nist["source"],
        "outcomes": [entry(o) for o in nist["outcomes"]],
    }


def problems(nist: dict[str, Any], tiers: dict[str, Any], built: dict[str, Any]) -> list[str]:
    """The drift check (CSF spec 4): NIST's fields in the built file equal the extract, every control is an
    SP 800-53 rev5 identifier, the tiers name real outcomes once, and the built file is not stale."""
    p: list[str] = []
    ids = [o["id"] for o in nist["outcomes"]]
    if len(ids) != OUTCOMES:
        p.append(f"{len(ids)} outcomes in NIST's extract, expected {OUTCOMES}")
    p += [f"duplicate outcome {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for o in nist["outcomes"]:
        p += [
            f"{o['id']}: {c} is not an SP 800-53 rev5 identifier"
            for c in o["related_controls"]
            if not CONTROL.fullmatch(c)
        ]
    checked, ask = tiers.get("checked") or {}, tiers.get("ask") or {}
    for tier, questions in (("checked", checked), ("ask", ask)):
        p += [f"{tier} {i}: not a CSF 2.0 outcome" for i in questions if i not in ids]
        p += [
            f"{tier} {i}: the question must be ASCII and end with '?'"
            for i, q in questions.items()
            if not (isinstance(q, str) and q.isascii() and q.rstrip().endswith("?"))
        ]
    p += [f"{i}: in both checked and ask" for i in sorted(set(checked) & set(ask))]
    parts, extra = tiers.get("parts") or {}, tiers.get("paraphrase_words") or {}
    text = {o["id"]: (o["outcome"], f"{o['outcome']} {o['category']}") for o in nist["outcomes"]}
    p += [f"parts {i}: not a checked outcome" for i in parts if i not in checked]
    p += [f"paraphrase_words {i}: not a checked outcome" for i in extra if i not in checked]
    for i in (i for i in checked if i in text):
        mapping = extra.get(i) or {}
        if not isinstance(mapping, dict):
            p.append(f"paraphrase_words {i}: must map each word to a NIST word")
            mapping = {}
        p += _part_problems(i, parts.get(i) or [], mapping, *text[i])
    want = build(nist, tiers)
    have = {o["id"]: o for o in built.get("outcomes", [])}
    for o in want["outcomes"]:
        h = have.get(o["id"])
        if h is None:
            p.append(f"{o['id']}: missing from csf-2.0.json")
            continue
        p += [f"{o['id']}: {k} differs from NIST's extract" for k in NIST_FIELDS if h.get(k) != o[k]]
    p += [f"{i}: not in NIST's extract" for i in have if i not in ids]
    if not p and built != want:
        p.append("csf-2.0.json is stale: run python -m datakit.csf build")
    return p


def load() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    built = json.loads(BUILT.read_text(encoding="utf-8")) if BUILT.exists() else {}
    return json.loads(EXTRACT.read_text(encoding="utf-8")), load_yaml_raw(TIERS), built


def check() -> list[str]:
    return problems(*load())


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("xlsx", type=Path)
    ex.add_argument("--retrieved", required=True, type=date.fromisoformat)
    sub.add_parser("build")
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        _write(EXTRACT, extract_file(args.xlsx, args.retrieved.isoformat()))
        print(f"wrote {EXTRACT.relative_to(ROOT)}")
        return 0
    nist, tiers, _ = load()
    _write(BUILT, build(nist, tiers))
    found = check()
    for x in found:
        print(x, file=sys.stderr)
    print(f"wrote {BUILT.relative_to(ROOT)}: {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())

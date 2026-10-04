"""Independent key verification.

python -m datakit.compare prepare dev OUT_DIR   # the verifier's folder: documents, metadata, questions only
                                                # (OUT_DIR must be new or empty)
python -m datakit.compare diff KEY VERIFY       # where the verifier and the derived key disagree
"""

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from datakit.extract import lines_of
from datakit.schemas import Facts, Key, Selection, load_yaml

ROOT = Path(__file__).resolve().parent.parent


class _Verification(BaseModel):
    """The verifier's file: {"items": [{"code", "label", "value", "evidence": [{"doc", "quote"}], "notes"}]}.
    Read through load_yaml so that a bare Yes or No stays a word (YAML 1.1 would make it a boolean)."""

    items: list[dict[str, Any]]


def prepare(pack: str, out: Path) -> None:
    if out.exists() and any(out.iterdir()):  # a leftover file would reach the verifier
        raise SystemExit(f"{out} is not empty: prepare needs a new or empty folder")
    facts = load_yaml(ROOT / "data" / pack / "facts.yaml", Facts)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    for d in facts.documents:
        lines = lines_of(ROOT / "data" / pack / "docs" / d.filename)
        numbered = "\n".join(f"{n}: {line}" for n, line in enumerate(lines, start=1))
        (out / "docs" / f"{d.filename}.txt").write_text(numbered + "\n", encoding="utf-8")
    with (out / "documents.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "kind", "status", "date", "scope", "evidence_allowed"])
        for d in facts.documents:
            w.writerow(
                [
                    d.filename,
                    d.kind,
                    d.status,
                    d.dated or "",
                    d.scope or "",
                    "yes" if d.evidence_allowed else "no",
                ]
            )
    for name in ("vsq-a", "mvsp-b"):
        sel = load_yaml(ROOT / "data" / "questionnaires" / f"{name}.selection.yaml", Selection)
        with (out / f"questions-{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["code", "question"])
            w.writerows([i.code, i.question] for i in sel.items)


def compare(key: Key, verification: dict[str, Any]) -> list[str]:
    given = verification.get("items", [])
    theirs = {i["code"]: i for i in given}
    repeats = Counter(i["code"] for i in given)
    out: list[str] = []
    for item in key.items:
        v = theirs.get(item.code)
        if v is None:
            out.append(f"{item.code}: verifier gave no answer")
        elif repeats[item.code] > 1:  # which of two answers counts is not ours to guess
            out.append(f"{item.code}: verifier answered more than once")
        elif (v.get("label"), v.get("value")) != (item.expected_label, item.expected_value):
            out.append(
                f"{item.code}: key {item.expected_label}/{item.expected_value}, "
                f"verifier {v.get('label')}/{v.get('value')} - {v.get('notes', '')}"
            )
    asked = {item.code for item in key.items}
    return out + [f"{code}: not in the key" for code in theirs if code not in asked]


def main(argv: list[str]) -> int:
    match argv:
        case ["prepare", pack, out]:
            prepare(pack, Path(out))
        case ["diff", key, verify]:
            found = compare(load_yaml(Path(key), Key), load_yaml(Path(verify), _Verification).model_dump())
            print("\n".join(found) or "no disagreements")
        case _:
            raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

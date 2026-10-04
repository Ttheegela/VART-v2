"""Mechanical checks over data/. CI runs `python -m datakit.validate all`.

python -m datakit.validate facts|docs|questionnaires|keys|mapper|all [--pack dev]
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

Check = Callable[[str], list[str]]
STAGES: dict[str, Check] = {}


def stage(name: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        STAGES[name] = fn
        return fn

    return register


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

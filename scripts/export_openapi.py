"""Write the API's OpenAPI schema to openapi.json (committed). The frontend generates its types from it, and
CI fails when either file is stale."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `python scripts/export_openapi.py` puts scripts/, not the repo root, on sys.path.
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

OUT = ROOT / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_a_bare_openrouter_key_is_a_finding() -> None:
    rules = {r["id"]: r for r in tomllib.loads((ROOT / ".gitleaks.toml").read_text())["rules"]}
    rule = re.compile(rules["openrouter-api-key"]["regex"])
    fake = "sk-or-" + "v1-" + "0123456789abcdef" * 4  # built from parts: no key-shaped literal in this file
    assert rule.search(f'OPENROUTER_API_KEY="{fake}"')
    assert rule.search(f"key {fake} in a log line")
    assert not rule.search("sk-or-v1-tooshort")

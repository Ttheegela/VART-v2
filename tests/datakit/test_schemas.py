from pathlib import Path

import pytest
from pydantic import ValidationError

from datakit.schemas import SCOPES, DocSpec, Facts, Statement, dump_yaml, load_yaml

MINIMAL = {
    "pack": "t",
    "company": {
        "name": "Zed",
        "legal_name": "Zed, Inc.",
        "domain": "zed.example",
        "product": "Zed App",
        "employees": 10,
        "hosting": "AWS us-east-1",
    },
    "buyer": "Buyer Co",
    "people": [{"name": "A B", "role": "Head of Security", "email": "ab@zed.example"}],
    "documents": [{"id": "isp", "filename": "isp.docx", "format": "docx", "kind": "policy"}],
    "controls": [{"id": "c1", "topic": "Governance", "truth": "There is a program."}],
    "statements": [
        {"id": "s1", "doc": "isp", "text": "Zed has a program.", "control": "c1", "stance": "yes"}
    ],
    "traps": [],
}


def test_minimal_facts_load(tmp_path: Path) -> None:
    path = tmp_path / "facts.yaml"
    dump_yaml(MINIMAL, path)
    facts = load_yaml(path, Facts)
    assert facts.doc("isp").status == "final" and facts.doc("isp").evidence_allowed is True
    assert [s.id for s in facts.statements_for("c1")] == ["s1"]


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Statement.model_validate(
            {"id": "s", "doc": "d", "text": "t", "control": None, "stance": "yes", "x": 1}
        )


def test_scope_vocabulary() -> None:
    assert "internal-systems" in SCOPES and "customer-product" in SCOPES
    with pytest.raises(ValidationError):
        DocSpec.model_validate(
            {"id": "a", "filename": "a.md", "format": "md", "kind": "policy", "scope": "Prod"}
        )


def test_dated_prefers_as_of_then_period_end_then_effective() -> None:
    d = DocSpec.model_validate(
        {
            "id": "a",
            "filename": "a.xlsx",
            "format": "xlsx",
            "kind": "record",
            "effective_date": "2026-01-01",
            "as_of": "2026-09-15",
        }
    )
    assert str(d.dated) == "2026-09-15"

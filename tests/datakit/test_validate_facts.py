import typing
from pathlib import Path

import pytest

from datakit import validate
from datakit.schemas import SCOPES, DocSpec, Facts, Scope, Statement, load_yaml
from datakit.validate import DATA, MIN_TRAPS, check_facts


def _facts() -> Facts:
    return load_yaml(DATA / "dev" / "facts.yaml", Facts)


def test_the_dev_fact_sheet_is_valid() -> None:
    assert check_facts(_facts()) == []


def test_every_trap_kind_meets_its_minimum() -> None:
    kinds = [t.kind for t in _facts().traps]
    for kind, minimum in MIN_TRAPS.items():
        assert kinds.count(kind) >= minimum, kind


def test_a_broken_fact_sheet_is_reported() -> None:
    f = _facts()
    broken = f.model_copy(
        update={"statements": (*f.statements, f.statements[0].model_copy(update={"doc": "nope"}))}
    )
    assert any("nope" in p for p in check_facts(broken))


def test_a_negation_statement_cannot_say_yes_anywhere_in_the_sheet() -> None:
    # in no trap: spec 6.7 rule 4 would turn it into a partial, which the key derivation does not do
    f = _facts()
    bad = f.statements[0].model_copy(update={"id": "bad", "flags": ("negation",), "stance": "yes"})
    broken = f.model_copy(update={"statements": (*f.statements, bad)})
    assert check_facts(broken) == ["statement bad: a statement flagged negation cannot have stance yes"]


@pytest.mark.parametrize("stance", ["yes", "no", "partial"])
def test_a_bare_stance_loads_as_the_string(tmp_path: Path, stance: str) -> None:
    path = tmp_path / "s.yaml"
    path.write_text(f"id: s1\ndoc: isp\ntext: A sentence.\ncontrol: c1\nstance: {stance}\n", encoding="utf-8")
    assert load_yaml(path, Statement).stance == stance


def test_a_bare_no_is_still_false_for_a_flag(tmp_path: Path) -> None:
    path = tmp_path / "d.yaml"
    path.write_text(
        "id: msa\nfilename: msa.docx\nformat: docx\nkind: contract\nevidence_allowed: no\n", encoding="utf-8"
    )
    assert load_yaml(path, DocSpec).evidence_allowed is False


def test_dated_prefers_period_end_over_effective_date_without_as_of() -> None:
    d = DocSpec.model_validate(
        {
            "id": "a",
            "filename": "a.pdf",
            "format": "pdf",
            "kind": "report",
            "effective_date": "2026-01-01",
            "period_end": "2026-06-30",
        }
    )
    assert str(d.dated) == "2026-06-30"


def test_the_scope_vocabulary_is_the_scope_type() -> None:
    assert typing.get_args(Scope) == SCOPES


def test_main_exits_1_and_prints_the_problem_when_a_stage_reports_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(validate.STAGES, "demo", lambda pack: [f"{pack} is broken"])
    assert validate.main(["demo"]) == 1
    captured = capsys.readouterr()
    assert "demo: dev is broken" in captured.err
    assert "datakit.validate demo: 1 problems" in captured.out


def test_main_exits_0_when_a_stage_reports_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(validate.STAGES, "demo", lambda pack: [])
    assert validate.main(["demo"]) == 0
    assert "0 problems" in capsys.readouterr().out

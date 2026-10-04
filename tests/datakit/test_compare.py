import csv
from pathlib import Path

import pytest

from datakit.compare import compare, main
from datakit.extract import lines_of
from datakit.schemas import Facts, Key, KeyEvidence, KeyItem, Label, Selection, Value, dump_yaml, load_yaml
from datakit.validate import DATA


def _item(code: str, label: Label, value: Value | None) -> KeyItem:
    return KeyItem(
        code=code,
        expected_label=label,
        expected_value=value,
        must_ask=False,
        evidence=(KeyEvidence(doc="acp", quote="MFA is required.", stance="yes"),),
        conflict_trap=None,
        scope_note_expected=False,
        honest_negative=False,
        traps=(),
        fills=(),
    )


def _key(*items: KeyItem) -> Key:
    return Key(pack="dev", questionnaire="vsq-a", items=items or (_item("VSQ-01", "verified", "Yes"),))


def test_agreement_is_silent() -> None:
    v = {"items": [{"code": "VSQ-01", "label": "verified", "value": "Yes", "evidence": [], "notes": ""}]}
    assert compare(_key(), v) == []


def test_label_and_value_disagreements_are_reported() -> None:
    v = {
        "items": [
            {
                "code": "VSQ-01",
                "label": "partial",
                "value": "Partial",
                "evidence": [],
                "notes": "says 'where possible'",
            }
        ]
    }
    assert compare(_key(), v) == [
        "VSQ-01: key verified/Yes, verifier partial/Partial - says 'where possible'"
    ]


def test_missing_items_are_reported() -> None:
    assert compare(_key(), {"items": []}) == ["VSQ-01: verifier gave no answer"]


def test_a_verified_no_against_a_verified_yes_is_a_disagreement() -> None:
    v = {
        "items": [{"code": "VSQ-01", "label": "verified", "value": "No", "evidence": [], "notes": "says no"}]
    }
    assert compare(_key(), v) == ["VSQ-01: key verified/Yes, verifier verified/No - says no"]


def test_conflict_and_unknown_differ_though_neither_has_a_value() -> None:
    v = {"items": [{"code": "VSQ-01", "label": "unknown", "value": None, "notes": "nothing found"}]}
    assert compare(_key(_item("VSQ-01", "conflict", None)), v) == [
        "VSQ-01: key conflict/None, verifier unknown/None - nothing found"
    ]


def test_an_omitted_value_agrees_with_a_key_that_has_none() -> None:
    key = _key(_item("VSQ-01", "conflict", None), _item("VSQ-02", "unknown", None))
    v = {
        "items": [
            {"code": "VSQ-01", "label": "conflict", "value": None},
            {"code": "VSQ-02", "label": "unknown"},
        ]
    }
    assert compare(key, v) == []


def _diff_args(tmp_path: Path, key: Key, verification: str) -> list[str]:
    dump_yaml(key, tmp_path / "key.yaml")
    (tmp_path / "verify.yaml").write_text(verification, encoding="utf-8")
    return ["diff", str(tmp_path / "key.yaml"), str(tmp_path / "verify.yaml")]


def test_diff_reads_an_unquoted_yes_and_no_as_the_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # YAML 1.1 would load a bare Yes or No as a boolean and report every verified answer as a disagreement
    argv = _diff_args(
        tmp_path,
        _key(_item("VSQ-01", "verified", "Yes"), _item("VSQ-02", "verified", "No")),
        "items:\n"
        "  - {code: VSQ-01, label: verified, value: Yes, evidence: [], notes: ''}\n"
        "  - {code: VSQ-02, label: verified, value: No, evidence: [], notes: ''}\n",
    )
    assert main(argv) == 0
    assert capsys.readouterr().out == "no disagreements\n"


def test_diff_prints_each_disagreement(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = _diff_args(
        tmp_path,
        _key(_item("VSQ-01", "verified", "Yes"), _item("VSQ-02", "verified", "No")),
        "items:\n  - {code: VSQ-01, label: partial, value: Partial, evidence: [], notes: where possible}\n",
    )
    assert main(argv) == 0
    assert capsys.readouterr().out == (
        "VSQ-01: key verified/Yes, verifier partial/Partial - where possible\n"
        "VSQ-02: verifier gave no answer\n"
    )


def test_an_unknown_command_prints_the_usage() -> None:
    with pytest.raises(SystemExit, match="datakit.compare prepare"):
        main(["verify"])


@pytest.fixture(scope="module")
def folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("verify")
    assert main(["prepare", "dev", str(out)]) == 0
    return out


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_the_verifier_folder_holds_documents_metadata_and_questions_only(folder: Path) -> None:
    facts = load_yaml(DATA / "dev" / "facts.yaml", Facts)
    assert sorted(p.name for p in folder.iterdir()) == [
        "docs",
        "documents.csv",
        "questions-mvsp-b.csv",
        "questions-vsq-a.csv",
    ]
    assert sorted(p.name for p in (folder / "docs").iterdir()) == sorted(
        f"{d.filename}.txt" for d in facts.documents
    )


def test_every_document_is_numbered_from_one(folder: Path) -> None:
    facts = load_yaml(DATA / "dev" / "facts.yaml", Facts)
    for d in facts.documents:
        shown = (folder / "docs" / f"{d.filename}.txt").read_text(encoding="utf-8").splitlines()
        lines = lines_of(DATA / "dev" / "docs" / d.filename)
        assert shown == [f"{n}: {line}" for n, line in enumerate(lines, start=1)], d.filename


def test_documents_csv_carries_only_what_the_verifier_rules_need(folder: Path) -> None:
    rows = {r["filename"]: r for r in _rows(folder / "documents.csv")}
    assert set(rows) == {d.filename for d in load_yaml(DATA / "dev" / "facts.yaml", Facts).documents}
    assert rows["access-control-policy.docx"] == {
        "filename": "access-control-policy.docx",
        "kind": "policy",
        "status": "final",
        "date": "2026-02-01",
        "scope": "internal-systems",
        "evidence_allowed": "yes",
    }
    assert rows["incident-response-policy-DRAFT.docx"]["status"] == "draft"
    assert rows["incident-response-policy-DRAFT.docx"]["date"] == ""
    assert rows["master-services-agreement-template.docx"]["evidence_allowed"] == "no"


def test_the_questions_files_carry_only_the_code_and_the_question(folder: Path) -> None:
    for name in ("vsq-a", "mvsp-b"):
        sel = load_yaml(DATA / "questionnaires" / f"{name}.selection.yaml", Selection)
        assert _rows(folder / f"questions-{name}.csv") == [
            {"code": i.code, "question": i.question} for i in sel.items
        ]

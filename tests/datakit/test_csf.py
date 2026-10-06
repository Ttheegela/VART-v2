import json
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from datakit import csf
from datakit.schemas import load_yaml_raw
from datakit.validate import STAGES


def _committed() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        json.loads(csf.EXTRACT.read_text(encoding="utf-8")),
        load_yaml_raw(csf.TIERS),
        json.loads(csf.BUILT.read_text(encoding="utf-8")),
    )


def _workbook(path: Path, rows: list[list[object]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CSF 2.0"
    ws.append([None, "The NIST Cybersecurity Framework 2.0"])
    ws.append(["Function", "Category", "Subcategory", "Implementation Examples", "Informative References"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_the_committed_data_matches_nists_extract() -> None:
    assert csf.check() == []
    assert STAGES["csf"]("dev") == []


def test_all_106_outcomes_are_kept_in_nists_order_with_the_proposed_tiers() -> None:
    nist, _, built = _committed()
    ids = [o["id"] for o in built["outcomes"]]
    assert ids == [o["id"] for o in nist["outcomes"]] and len(ids) == csf.OUTCOMES
    assert {o["function"] for o in built["outcomes"]} == {
        "Govern",
        "Identify",
        "Protect",
        "Detect",
        "Respond",
        "Recover",
    }
    assert Counter(o["tier"] for o in built["outcomes"]) == {"checked": 29, "ask": 5, "not_checked": 72}
    assert built["csf_version"] == "2.0" and built["source"] == csf.DOWNLOAD_URL


def test_a_changed_nist_field_is_named_with_its_outcome() -> None:
    nist, tiers, built = _committed()
    built["outcomes"][0]["outcome"] += " (edited)"
    first = built["outcomes"][0]["id"]
    assert csf.problems(nist, tiers, built) == [f"{first}: outcome differs from NIST's extract"]


def test_an_outcome_missing_from_the_built_file_is_named() -> None:
    nist, tiers, built = _committed()
    gone = built["outcomes"].pop()["id"]
    assert f"{gone}: missing from csf-2.0.json" in csf.problems(nist, tiers, built)


def test_a_control_that_is_not_an_sp_800_53_identifier_is_named() -> None:
    nist, tiers, built = _committed()
    nist["outcomes"][0]["related_controls"].append("AC-2")
    first = nist["outcomes"][0]["id"]
    assert f"{first}: AC-2 is not an SP 800-53 rev5 identifier" in csf.problems(nist, tiers, built)


@pytest.mark.parametrize("control", ["AC-02", "CP-02(08)", "PT", "SA-15(13)"])
def test_controls_enhancements_and_families_are_identifiers(control: str) -> None:
    assert csf.CONTROL.fullmatch(control)


@pytest.mark.parametrize("control", ["AC-2", "ac-02", "AC-02(8)", "AC-02 ", "A.5.15"])
def test_other_strings_are_not_identifiers(control: str) -> None:
    assert not csf.CONTROL.fullmatch(control)


def test_tiers_name_real_outcomes_once_with_ascii_questions() -> None:
    nist, tiers, built = _committed()
    first_checked = next(iter(tiers["checked"]))
    tiers["ask"]["XX.YY-01"] = "Is it done?"
    tiers["ask"][first_checked] = "Is it done?"
    tiers["checked"][first_checked] = "Is it done"
    found = csf.problems(nist, tiers, built)
    assert "ask XX.YY-01: not a CSF 2.0 outcome" in found
    assert f"{first_checked}: in both checked and ask" in found
    assert f"checked {first_checked}: the question must be ASCII and end with '?'" in found


def test_extract_reads_nists_layout_and_skips_withdrawn_rows(tmp_path: Path) -> None:
    path = tmp_path / "csf.xlsx"
    refs = "\n".join(
        [
            "ISO/IEC 27001:2022: A.5.15",
            "SP 800-53 Rev 5.1.1: AC-01",
            "SP 800-53 Rev 5.2.0: AC-01",
            "SP 800-53 Rev 5.2.0: AC-02(01)",
            "SP 800-53 Rev 5.2.0: AC-01",
        ]
    )
    _workbook(
        path,
        [
            [
                "PROTECT (PR): Safeguards to manage the organization's cybersecurity risks are used",
                None,
                None,
            ],
            [
                None,
                "Identity Management, Authentication and Access Control (PR.AC): [Withdrawn: Moved to PR.AA]",
            ],
            [None, "Identity Management, Authentication, and Access Control (PR.AA): Access is limited"],
            [
                None,
                None,
                "PR.AA-05: Access permissions are defined in a policy and reviewed ",
                "Ex1: x",
                refs,
            ],
            [None, None, "PR.AA-07: [Withdrawn: Incorporated into PR.AA-05]", None, None],
        ],
    )
    assert csf.extract(path) == [
        {
            "id": "PR.AA-05",
            "function": "Protect",
            "category": "Identity Management, Authentication, and Access Control",
            "outcome": "Access permissions are defined in a policy and reviewed",
            "related_controls": ["AC-01", "AC-02(01)"],
        }
    ]


def test_extract_refuses_an_export_without_sp_800_53_references(tmp_path: Path) -> None:
    path = tmp_path / "csf.xlsx"
    _workbook(
        path,
        [
            ["PROTECT (PR): Safeguards are used"],
            [None, "Data Security (PR.DS): Data are managed"],
            [None, None, "PR.DS-01: Data-at-rest is protected", None, "SP 800-53 Rev 6.0: SC-28"],
        ],
    )
    with pytest.raises(ValueError, match="SP 800-53 Rev 5.2.0"):
        csf.extract(path)

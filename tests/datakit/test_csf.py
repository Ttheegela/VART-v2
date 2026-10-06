import json
from collections import Counter
from collections.abc import Callable
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
    assert Counter(o["tier"] for o in built["outcomes"]) == {"checked": 31, "ask": 5, "not_checked": 70}
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


def test_inflections_of_nists_words_are_nist_words() -> None:
    nist = "Inventories of hardware managed by the organization are maintained; processes are established"
    assert csf.added_words("Is an inventory of hardware maintained, and are processes managed?", nist) == []
    assert csf.added_words("Is hardware encrypted by the vendor?", nist) == ["encrypted", "vendor"]


def test_every_checked_outcome_has_parts_and_no_other_outcome_does() -> None:
    _, tiers, built = _committed()
    parts = {o["id"]: o["parts"] for o in built["outcomes"]}
    assert all(parts[i] for i in tiers["checked"]) and sum(map(len, parts.values())) == 73
    assert all(parts[o["id"]] == [] for o in built["outcomes"] if o["tier"] != "checked")
    assert all(len(m) <= csf.MAX_PARAPHRASE for m in tiers["paraphrase_words"].values())


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (lambda t: t["parts"].update({"PR.DS-11": []}), "checked PR.DS-11: no parts"),
        (lambda t: t["parts"].update({"GV.OC-01": ["Is it done?"]}), "parts GV.OC-01: not a checked outcome"),
        (
            lambda t: t["parts"].update({"RS.MI-01": ["Are incidents contained by the security team?"]}),
            "RS.MI-01 part 1: adds 'security', not in NIST's text",
        ),
        (  # a document name is an added word
            lambda t: t["parts"]["GV.PO-01"].append("Is the policy enforced, as the HR handbook says?"),
            "GV.PO-01 part 4: adds 'hr', not in NIST's text",
        ),
        (
            lambda t: t["parts"].update({"RS.MI-01": ['Are incidents "contained"?']}),
            "RS.MI-01 part 1: must be ASCII, quote nothing and end with '?'",
        ),
        (  # Ruling 11b: separation of duties may not be dropped
            lambda t: t["parts"].update(
                {"PR.AA-05": [q.replace(" and separation of duties", "") for q in t["parts"]["PR.AA-05"]]}
            ),
            "PR.AA-05: NIST's 'separation' is in no part",
        ),
        (
            lambda t: t["paraphrase_words"].pop("ID.AM-08"),
            "ID.AM-08 part 1: adds 'acquisition', not in NIST's text",
        ),
        (
            lambda t: t["paraphrase_words"].update({"RS.MI-01": {"isolation": "contained"}}),
            "RS.MI-01: paraphrase word 'isolation' is in no part",
        ),
        (  # I3: a paraphrase word names an instance of a NIST word of its own outcome
            lambda t: t["paraphrase_words"]["RC.RP-01"].update({"failover": "bcp"}),
            "RC.RP-01: paraphrase word 'failover' must map to a word of NIST's text, not 'bcp'",
        ),
        (
            lambda t: t["paraphrase_words"]["PR.PS-06"].update({"sast": "practices"}),
            "PR.PS-06: 4 paraphrase words, at most 3",
        ),
        (  # an added word enters only through an example clause
            lambda t: t["parts"]["PR.PS-04"].__setitem__(
                1, "Are log records made available centrally for continuous monitoring?"
            ),
            "PR.PS-04 part 2: 'centrally' stands outside an example clause",
        ),
        (  # R3: the clause ends at the next comma
            lambda t: t["parts"]["PR.PS-01"].__setitem__(
                0,
                "Are configuration management practices, such as baseline configurations,"
                " established with change control?",
            ),
            "PR.PS-01 part 1: 'change' stands outside an example clause",
        ),
        (  # R4: the revision-1 list form is named, not a crash
            lambda t: t["paraphrase_words"].update({"PR.DS-01": ["encryption"]}),
            "paraphrase_words PR.DS-01: must map each word to a NIST word",
        ),
    ],
)
def test_a_bad_part_is_named(edit: Callable[[dict[str, Any]], object], problem: str) -> None:
    nist, tiers, _ = _committed()
    edit(tiers)
    assert problem in csf.problems(nist, tiers, csf.build(nist, tiers))

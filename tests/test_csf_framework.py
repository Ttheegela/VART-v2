import uuid
from collections import Counter

import pytest

from app import csf
from app.contracts import ItemInput


def _one(tier: str) -> csf.Outcome:
    return next(o for o in csf.framework().outcomes if o.tier == tier)


def test_the_framework_holds_every_outcome_with_its_tier() -> None:
    fw = csf.framework()
    assert (len(fw.outcomes), fw.version) == (106, "2.0")
    assert Counter(o.tier for o in fw.outcomes) == {"checked": 31, "ask": 5, "not_checked": 70}
    assert all(o.question for o in fw.outcomes if o.tier != "not_checked")
    assert all(o.question is None for o in fw.outcomes if o.tier == "not_checked")
    assert fw.get("PR.AA-05").function == "Protect" and "AC-06" in fw.get("PR.AA-05").related_controls
    with pytest.raises(KeyError):
        fw.get("PR.AA-99")


@pytest.mark.parametrize(
    ("label", "value", "want"),
    [
        ("verified", "Yes", "covered"),
        ("partial", "Partial", "partly_covered"),
        ("verified", "No", "not_met"),
        ("conflict", None, "documents_disagree"),
        ("unknown", None, "gap"),
        ("na", None, None),
        (None, None, None),  # not run yet
    ],
)
def test_gap_labels_map_decides_output_as_the_spec_table_says(
    label: str | None, value: str | None, want: str | None
) -> None:
    assert csf.gap_label(_one("checked"), label, value) == want  # type: ignore[arg-type]


def test_ask_me_is_confirmed_only_with_a_stored_statement() -> None:
    ask = _one("ask")
    assert csf.gap_label(ask, "user_confirmed", None, uuid.uuid4()) == "confirmed_by_you"
    assert csf.gap_label(ask, "user_confirmed", None, None) == "not_answered"
    assert csf.gap_label(ask, None) == "not_answered"
    assert (
        csf.gap_label(ask, "verified", "Yes") == "not_answered"
    )  # a document label never confirms an Ask-me
    assert csf.gap_label(_one("checked"), "user_confirmed", None, uuid.uuid4()) == "confirmed_by_you"


def test_not_checked_outcomes_never_carry_a_label() -> None:
    o = _one("not_checked")
    for label, value in (("verified", "Yes"), ("unknown", None), ("user_confirmed", None), (None, None)):
        assert csf.gap_label(o, label, value, uuid.uuid4()) is None  # type: ignore[arg-type]


def test_every_label_has_its_display_words() -> None:
    assert csf.GAP_WORDS == {
        "covered": "Covered",
        "partly_covered": "Partly covered",
        "not_met": "Not met (stated)",
        "documents_disagree": "Documents disagree",
        "gap": "Gap",
        "confirmed_by_you": "Confirmed by you",
        "not_answered": "Not answered",
    }


def test_a_scope_is_the_core_or_one_function() -> None:
    core = csf.in_scope("core")
    assert len(core) == 36 and all(o.tier != "not_checked" for o in core)
    assert {o.function for o in csf.in_scope("protect")} == {"Protect"}
    assert Counter(o.tier for o in csf.in_scope("govern")) == {"checked": 2, "ask": 5}
    for bad in ("Protect", "all", ""):
        with pytest.raises(ValueError, match="unknown scope"):
            csf.in_scope(bad)


def test_an_outcome_is_asked_as_its_question_with_its_category_as_topic() -> None:
    o = csf.framework().get("PR.DS-01")
    assert csf.item_input(o) == ItemInput("PR.DS-01", o.question, "Data Security")
    with pytest.raises(ValueError, match="no question"):
        csf.item_input(_one("not_checked"))

import json
from datetime import date

import pytest

from app.contracts import Citation, Conflict, ConflictSide, Decision, ItemInput
from app.draft import check, plain_name, template_answer, user_prompt, write_draft
from app.llm.client import LLMError
from app.llm.recorder import ReplayMiss
from tests.fakes import FakeLLM

DOCS = ["access-control-policy.docx", "access-review-records.xlsx", "business-continuity-policy.md"]
POLICY = Citation(
    "c1",
    "d1",
    "access-control-policy.docx",
    16,
    16,
    "User access to internal systems is reviewed quarterly.",
    "yes",
)
LOG = Citation(
    "c2",
    "d2",
    "access-review-records.xlsx",
    4,
    4,
    "System: Okta; Last review completed: 2026-01-10; Status: Overdue",
    "no",
)
VERIFIED = Decision("verified", "Yes", (POLICY,), (), None, None, 0.9)
CONFLICT = Decision(
    "conflict",
    None,
    (POLICY, LOG),
    (),
    Conflict(
        "date",
        (ConflictSide("no", (LOG,), date(2026, 9, 15)), ConflictSide("yes", (POLICY,), date(2026, 2, 1))),
    ),
    None,
    0.3,
)
SCOPED = Decision(
    "partial",
    "Partial",
    (POLICY, LOG),
    (),
    None,
    "Yes for internal systems (access-control-policy.docx); no for employees (access-review-records.xlsx).",
    0.6,
)
ITEM = ItemInput("VSQ-09", "Do you review access at least quarterly?", "Access Control")


def _yes(step: str) -> bool:
    return True


def test_plain_names_drop_extensions_years_and_draft_markers() -> None:
    assert plain_name("incident-response-policy-DRAFT.docx") == "incident response policy"
    assert plain_name("penetration-test-report-2026.pdf") == "penetration test report"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ('The policy says access is "reviewed every month".', "quote not in the evidence"),
        ("The access control policy says reviews happen every 90 days.", "number not in the evidence: 90"),
        (
            "The business continuity policy says so.",
            "names a document it does not cite: business continuity policy",
        ),
        ("", "the answer is empty"),
    ],
)
def test_the_check_finds_unsupported_quotes_numbers_and_names(text: str, problem: str) -> None:
    assert any(p.startswith(problem) for p in check(text, VERIFIED, DOCS))


def test_a_faithful_answer_passes_the_check() -> None:
    text = 'Yes. The access control policy says "User access to internal systems is reviewed quarterly."'
    assert check(text, VERIFIED, DOCS) == []


@pytest.mark.parametrize("decision", [VERIFIED, CONFLICT, SCOPED])
def test_the_template_answer_always_passes_the_check(decision: Decision) -> None:
    text = template_answer(decision)
    assert text and check(text, decision, DOCS) == []


def test_the_conflict_template_names_the_newer_record_first_and_asks() -> None:
    text = template_answer(CONFLICT)
    assert text.startswith("The documents disagree. The access review records (dated 2026-09-15) says:")
    assert text.endswith("Which is current?")


def test_the_prompt_lists_conflict_sides_in_order_with_dates() -> None:
    text = user_prompt(ITEM, CONFLICT)
    assert "Conflict, rule date: side 1 is the newer record." in text
    assert text.index("Side 1:") < text.index("2026-09-15") < text.index("Side 2:") < text.index("2026-02-01")


def test_unknown_items_get_no_draft_and_no_call() -> None:
    unknown = Decision("unknown", None, (), (), None, None, 0.0)
    assert write_draft(FakeLLM([]), ITEM, unknown, "m", _yes, DOCS).source == "none"


def test_a_good_first_draft_is_kept() -> None:
    text = 'Yes. The access control policy says "User access to internal systems is reviewed quarterly."'
    good = json.dumps({"text": text})
    d = write_draft(FakeLLM([good]), ITEM, VERIFIED, "m/draft", _yes, DOCS)
    assert (d.source, d.problems) == ("model", ())


def test_a_bad_draft_is_retried_once_with_its_problems() -> None:
    bad = json.dumps({"text": "Yes, every 30 days."})
    good = json.dumps({"text": "Yes, according to the access control policy."})
    llm = FakeLLM([bad, good])
    d = write_draft(llm, ITEM, VERIFIED, "m/draft", _yes, DOCS)
    assert d.source == "model" and d.problems == ("number not in the evidence: 30",)
    assert "number not in the evidence: 30" in llm.requests[1].user


def test_two_bad_drafts_fall_back_to_the_template() -> None:
    bad = json.dumps({"text": "Yes, every 30 days."})
    d = write_draft(FakeLLM([bad, bad]), ITEM, VERIFIED, "m", _yes, DOCS)
    assert d.source == "template" and d.text == template_answer(VERIFIED)


def test_a_failed_call_or_a_refused_budget_falls_back_to_the_template() -> None:
    assert (
        write_draft(FakeLLM([LLMError("draft: timeout")]), ITEM, VERIFIED, "m", _yes, DOCS).source
        == "template"
    )
    assert write_draft(FakeLLM([]), ITEM, VERIFIED, "m", lambda step: False, DOCS).source == "template"
    assert write_draft(None, ITEM, VERIFIED, "m", _yes, DOCS).source == "template"


def test_a_missing_recording_is_never_turned_into_a_template() -> None:
    with pytest.raises(ReplayMiss):
        write_draft(FakeLLM([ReplayMiss("draft: no recording")]), ITEM, VERIFIED, "m", _yes, DOCS)


def test_a_side_with_two_documents_is_dated_once_not_per_citation() -> None:
    # The side's date is its newest record's; Citation carries no date, so dating every citation with it
    # would misdate the other document (Task 4 review).
    ticket = Citation("c3", "d3", "access-review-tickets.csv", 2, 2, "Okta review not scheduled", "no")
    two = Decision(
        "conflict",
        None,
        (POLICY, LOG, ticket),
        (),
        Conflict(
            "date",
            (
                ConflictSide("no", (LOG, ticket), date(2026, 9, 15)),
                ConflictSide("yes", (POLICY,), date(2026, 2, 1)),
            ),
        ),
        None,
        0.3,
    )
    prompt = user_prompt(ITEM, two)
    assert prompt.count("2026-09-15") == 1
    assert "Side 1: dated 2026-09-15\n" in prompt
    assert all("dated" not in line for line in prompt.splitlines() if line.startswith("- "))
    text = template_answer(two)
    assert "The access review records (dated" not in text
    assert text.startswith(
        "The documents disagree. One side, dated 2026-09-15: The access review records says:"
    )
    assert "The access control policy (dated 2026-02-01) says:" in text
    assert check(text, two, [*DOCS, "access-review-tickets.csv"]) == []


def test_a_number_in_a_cited_file_name_is_evidence() -> None:
    report = Citation(
        "c4", "d4", "pen-test-report-2026.pdf", 3, 3, "No critical findings remain open.", "yes"
    )
    decision = Decision("verified", "Yes", (report,), (), None, None, 0.9)
    assert check("Yes. The 2026 pen test report says so.", decision, DOCS) == []
    assert check("Yes. The 2025 pen test report says so.", decision, DOCS) == [
        "number not in the evidence: 2025"
    ]

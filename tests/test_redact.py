from datetime import date

import pytest

from app.contracts import Line
from app.patterns import PLACEHOLDER
from app.redact import redact_lines, redact_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "The program is owned by Dana Ortiz, Head of Security.",
            "The program is owned by <PERSON>, Head of Security.",
        ),
        (
            "System: Okta; Owner: Marcus Lee; Status: Overdue",
            "System: Okta; Owner: <PERSON>; Status: Overdue",
        ),
        ("Write to dana.ortiz@kestrelyn.example today.", "Write to <EMAIL> today."),
        ("Call +1 512 555 0142 or (512) 555-0143.", "Call <PHONE> or <PHONE>."),
        ("Our office is at 1200 Congress Avenue, Suite 400.", "Our office is at <ADDRESS>."),
        ("db: postgres://admin:hunter2pass@db.example.com:5432/app", "db: <SECRET>"),
        ("key sk-or-v1-abcdefghijklmnopqrstuvwxyz012345", "key <SECRET>"),
        ("aws AKIAIOSFODNN7EXAMPLE", "aws <SECRET>"),
        ("password = hunter2hunter2", "<SECRET>"),
    ],
)
def test_private_data_and_secrets_are_replaced(text: str, expected: str) -> None:
    assert redact_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Kestrelyn maintains a documented incident response plan.",  # a company name is not a person
        "Kestrelyn Ledger stores all customer data in AWS us-east-1.",  # nor a product name
        "Sablecrest Security performed the test.",
        "Customer data is stored in Ireland.",  # place names stay: data-residency answers need them
        "Version 2.0 was released on 2026-01-10 for ISO 27001:2022.",  # dates and versions are not phones
        "Google Workspace and GitHub are reviewed quarterly.",
    ],
)
def test_business_text_is_left_alone(text: str) -> None:
    assert redact_text(text) == text


def test_a_private_key_block_is_one_secret() -> None:
    # Built in pieces so that no file holds a whole fake key block for gitleaks to match (Plan 2 addendum).
    key = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA " + "PRIVATE KEY-----"
    assert redact_text(f"before {key} after") == "before <SECRET> after"


def test_redaction_tokens_never_look_like_template_placeholders() -> None:
    text = redact_text("Owner: Marcus Lee; Contact: lee@example.com; Phone: 512 555 0142")
    assert "<PERSON>" in text and PLACEHOLDER.search(text) is None


def test_lines_keep_their_kind_and_date() -> None:
    (line,) = redact_lines([Line("Owner: Marcus Lee", "record", date(2026, 1, 10))])
    assert (line.text, line.kind, line.as_of) == ("Owner: <PERSON>", "record", date(2026, 1, 10))


def test_overlapping_matches_collapse_to_one_token() -> None:
    # the URL's user:password@host also looks like an email; only the outer span may be replaced
    text = "db: postgres://admin:hunter2pass@db.example.com/app done"
    assert redact_text(text) == "db: <SECRET> done"


def test_digits_glued_to_a_word_are_not_a_phone() -> None:
    assert redact_text("order A512 555 0142 shipped") == "order A512 555 0142 shipped"

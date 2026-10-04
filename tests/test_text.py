from datetime import date, datetime

from app.text import cell_text, contains, normalize, record_line


def test_normalize_straightens_quotes_dashes_and_spaces() -> None:
    assert normalize("  “Access” is reviewed — quarterly’s  ") == '"Access" is reviewed - quarterly\'s'


def test_normalize_folds_compatibility_characters() -> None:
    assert normalize("ﬁrewall") == "firewall"


def test_normalize_keeps_case() -> None:
    assert normalize("MFA") == "MFA"


def test_contains_ignores_layout_differences() -> None:
    text = "Access to production\nis reviewed   quarterly by the  Head of Security."
    assert contains(text, "is reviewed quarterly by the Head of Security")
    assert contains(text, "“Access to production is reviewed”".strip("“”"))


def test_contains_is_case_sensitive_and_rejects_empty_quotes() -> None:
    assert not contains("Access is reviewed quarterly.", "access is reviewed")
    assert not contains("Access is reviewed quarterly.", "   ")


def test_record_line_skips_empty_cells_and_formats_values() -> None:
    headers = ["System", "Owner", "Last review completed", "Users", "Notes"]
    values = ["Okta", None, datetime(2026, 1, 10), 42.0, ""]
    assert record_line(headers, values) == "System: Okta; Last review completed: 2026-01-10; Users: 42"


def test_record_line_names_missing_headers() -> None:
    assert record_line(["System"], ["AWS", "Overdue"]) == "System: AWS; Column 2: Overdue"


def test_cell_text_handles_dates_times_and_text() -> None:
    assert cell_text(date(2026, 9, 15)) == "2026-09-15"
    assert cell_text(datetime(2026, 9, 15, 13, 5)) == "2026-09-15 13:05"
    assert cell_text(3.5) == "3.5"
    assert cell_text("  On-premises file server ") == "On-premises file server"

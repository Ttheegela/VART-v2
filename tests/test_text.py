from datetime import date, datetime, time
from pathlib import Path

from app.text import cell_text, contains, normalize, record_line


def test_normalize_straightens_quotes_dashes_and_spaces() -> None:
    assert (
        normalize("  \u201cAccess\u201d is\u00a0reviewed \u2014 quarterly\u2019s  ")
        == '"Access" is reviewed - quarterly\'s'
    )


def test_normalize_folds_compatibility_characters() -> None:
    assert normalize("\ufb01rewall") == "firewall"


def test_normalize_keeps_case() -> None:
    assert normalize("MFA") == "MFA"


def test_contains_ignores_layout_differences() -> None:
    text = "Access to production\nis reviewed   quarterly by the  Head of Security."
    assert contains(text, "is reviewed quarterly by the Head of Security")
    assert contains(text, "Access to production is reviewed")
    assert contains('He said "MFA" is on', "\u201cMFA\u201d is on")


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
    assert cell_text("  On-premises\u00a0file server ") == "On-premises file server"


def test_contains_does_not_start_or_end_inside_a_word() -> None:
    assert not contains("Backups are unencrypted at rest.", "encrypted at rest")
    assert not contains("Yesterday the audit closed.", "Yes")
    assert contains("multi-factor auth", "factor auth")
    assert contains("quarterly.\u00b9 Next", "quarterly.")  # a footnote mark after punctuation still matches


def test_normalize_folds_hyphens_and_drops_invisible_characters() -> None:
    assert normalize("multi\u2010factor \u2011 \u2012 \u2015") == "multi-factor - - -"
    assert normalize("fire\u00adwall \u200bzero\u200c\u200d \ufeffbom \u200elrm") == "firewall zero bom lrm"
    assert normalize("hid\U000e0041\U000e0042den a\x02b") == "hidden ab"


def test_normalize_is_pinned() -> None:
    """Any change to the folding (translate table, Unicode database, Python version) changes which key quotes
    validate and which recorded citations pass. Recompute the digest only with the adversary review."""
    import hashlib
    import sys

    out = "\n".join(normalize(chr(c)) for c in range(sys.maxunicode + 1) if not 0xD800 <= c <= 0xDFFF)
    digest = hashlib.sha256(out.encode()).hexdigest()
    assert digest == "77d4af9b000f4d898832f34f62abad154cfa0f51858f52d1ee941d5a7dff112f"


def test_record_line_accepts_non_text_headers_and_cells() -> None:
    line = record_line([None, 2026, datetime(2026, 1, 1)], ["x", "y", "z"])
    assert line == "Column 1: x; 2026: y; 2026-01-01: z"
    assert record_line(["Enforced", "Checked"], [True, time(13, 5, 30)]) == "Enforced: TRUE; Checked: 13:05"


def test_text_module_is_ascii() -> None:
    module = Path(__file__).resolve().parent.parent / "app" / "text.py"
    assert module.read_text(encoding="utf-8").isascii()
    assert Path(__file__).read_text(encoding="utf-8").isascii()


def test_information_separators_and_nel_fold_to_spaces() -> None:
    # U+001C-001F are whitespace to str.split(); stripping them fused words (Plan 1A Task 1 minor).
    assert normalize("a\x1cb\x1dc\x1ed\x1fe") == "a b c d e"
    assert normalize("a\x85b") == "a b"


def test_normalize_drops_c1_controls_and_default_ignorables() -> None:
    hidden = [0x80, 0x9F, 0x34F, 0x61C, 0x115F, 0x180E, 0x2065, 0x3164, 0xFE0F, 0xFFA0, 0xFFF9, 0x1D173]
    assert normalize("x".join(chr(c) for c in hidden)) == "x" * (len(hidden) - 1)
    assert normalize("hid" + chr(0xE0101) + chr(0xE01EF) + "den") == "hidden"  # variation selectors 17-256
    assert normalize("quar" + chr(0xFFFE) + "terly") == "quarterly"  # a noncharacter is never visible


def test_a_quote_may_end_right_before_a_glued_footnote_digit() -> None:
    assert contains("Access is reviewed quarterly1 by IT.", "Access is reviewed quarterly")
    assert not contains("TLS 12 only", "TLS 1")  # a number still may not end inside a number
    assert not contains("Backups are unencrypted at rest.", "encrypted at rest")
    assert not contains("reviewed quarterlyx", "reviewed quarterly")


def test_a_quote_ending_in_a_letter_may_not_end_before_an_underscore() -> None:
    # Plan 2A Ruling 7: only a digit may follow; letters and underscore are mid-token.
    assert contains("MFA_enforced: false", "MFA") is False


def test_normalize_is_idempotent_on_every_code_point() -> None:
    import sys

    for c in range(sys.maxunicode + 1):
        if not 0xD800 <= c <= 0xDFFF:
            once = normalize(chr(c))
            assert normalize(once) == once, hex(c)

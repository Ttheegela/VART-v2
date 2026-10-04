"""Text rules shared by ingest, decide and the eval keys: how quotes are compared and how a table row becomes
one line. Every citation check depends on these, so changes here need the adversary review
(Plan 1A lane gate)."""

import re
import unicodedata
from collections.abc import Sequence
from datetime import date, datetime, time

_TRANSLATE = str.maketrans(
    {
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u201a": "'",  # single low-9 quotation mark
        "\u201b": "'",  # single high-reversed-9 quotation mark
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u201e": '"',  # double low-9 quotation mark
        "\u201f": '"',  # double high-reversed-9 quotation mark
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2212": "-",  # minus sign
        "\u2010": "-",  # hyphen (also what NFKC makes of the non-breaking hyphen U+2011)
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u2015": "-",  # horizontal bar
    }
)
_SPACE = re.compile(r"\s+")
# Never visible, never part of a quote, so stripped before NFKC: C0 and C1 controls that are not
# whitespace (the separators U+001C-001F and NEL U+0085 are whitespace and fold to a space instead) and
# the default-ignorable characters: soft hyphen, combining grapheme joiner, bidi and Arabic letter marks,
# Hangul fillers, zero-width characters, word joiner and invisible operators, variation selectors,
# byte-order mark, interlinear annotation marks, noncharacters U+FFFE-FFFF (pdfium writes U+FFFE for a
# hyphen at a line break), format and tag characters.
_INVISIBLE = re.compile(
    r"[\x00-\x08\x0e-\x1b\x7f-\x84\x86-\x9f\xad\U0000034f\U0000061c\U0000115f\U00001160\U000017b4\U000017b5"
    r"\U0000180b-\U0000180f\U0000200b-\U0000200f\U0000202a-\U0000202e\U00002060-\U0000206f\U00003164"
    r"\U0000fe00-\U0000fe0f\U0000feff\U0000ffa0\U0000fff0-\U0000fffb\U0000fffe\U0000ffff"
    r"\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]"
)
_WORD = re.compile(r"\w")


def normalize(text: str) -> str:
    """Invisible characters removed, NFKC, straight quotes, plain hyphens, single spaces, trimmed. Case is
    kept."""
    text = unicodedata.normalize("NFKC", _INVISIBLE.sub("", text)).translate(_TRANSLATE)
    return _SPACE.sub(" ", text).strip()


def contains(haystack: str, quote: str) -> bool:
    """True when the quote appears in the text after both are normalized and does not start or end inside a
    word. A quote ending in a letter may end right before a digit (a footnote mark that lost its superscript:
    "reviewed quarterly" in "reviewed quarterly1"). An empty quote never matches."""
    needle, text = normalize(quote), normalize(haystack)
    if not needle or needle not in text:
        return False
    head = r"(?<!\w)" if _WORD.match(needle[0]) else ""
    tail = ""
    if needle[-1].isalpha():
        tail = r"(?![^\W\d_])"  # no letter may follow; a digit may
    elif _WORD.match(needle[-1]):
        tail = r"(?!\w)"
    return re.search(head + re.escape(needle) + tail, text) is not None


def cell_text(value: object) -> str:
    """How one spreadsheet or table cell reads inside a record line."""
    if value is None:
        return ""
    if isinstance(value, bool):  # before the numeric checks (bool is an int); Excel and CSV show TRUE/FALSE
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):  # before date: datetime is a date subclass
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="minutes")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize(str(value))


def record_line(headers: Sequence[object], values: Sequence[object]) -> str:
    """One table row as one line: 'Header: value; Header: value'. Empty cells are skipped; a missing or blank
    header becomes 'Column N' (1-based). For reading, not parsing: '; ' and ': ' may occur inside values."""
    parts = []
    for i, value in enumerate(values):
        text = cell_text(value)
        if not text:
            continue
        header = cell_text(headers[i]) if i < len(headers) else ""
        parts.append(f"{header or f'Column {i + 1}'}: {text}")
    return "; ".join(parts)

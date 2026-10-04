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
# Never visible, never part of a quote: C0 controls that are not whitespace, soft hyphen, zero-width
# space/joiners, bidi marks, word joiner and invisible operators, byte-order mark, Unicode tag characters.
_INVISIBLE = re.compile(
    r"[\x00-\x08\x0e-\x1f\x7f\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]"
)
_WORD = re.compile(r"\w")


def normalize(text: str) -> str:
    """Invisible characters removed, NFKC, straight quotes, plain hyphens, single spaces, trimmed. Case is
    kept."""
    text = unicodedata.normalize("NFKC", _INVISIBLE.sub("", text)).translate(_TRANSLATE)
    return _SPACE.sub(" ", text).strip()


def contains(haystack: str, quote: str) -> bool:
    """True when the quote appears in the text after both are normalized and does not start or end inside a
    word. An empty quote never matches."""
    needle, text = normalize(quote), normalize(haystack)
    if not needle or needle not in text:
        return False
    head = r"(?<!\w)" if _WORD.match(needle[0]) else ""
    tail = r"(?!\w)" if _WORD.match(needle[-1]) else ""
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

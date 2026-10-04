"""Text rules shared by ingest, decide and the eval keys: how quotes are compared and how a table row becomes
one line. Every citation check depends on these, so changes here need the adversary review
(Plan 1A lane gate)."""

import re
import unicodedata
from collections.abc import Sequence
from datetime import date, datetime

_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "–": "-",
        "—": "-",
        "−": "-",
    }
)
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC, straight quotes, plain hyphens, single spaces, trimmed. Case is kept."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text).translate(_TRANSLATE)).strip()


def contains(haystack: str, quote: str) -> bool:
    """True when the quote appears in the text after both are normalized. An empty quote never matches."""
    needle = normalize(quote)
    return bool(needle) and needle in normalize(haystack)


def cell_text(value: object) -> str:
    """How one spreadsheet or table cell reads inside a record line."""
    if value is None:
        return ""
    if isinstance(value, datetime):  # before date: datetime is a date subclass
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize(str(value))


def record_line(headers: Sequence[str], values: Sequence[object]) -> str:
    """One table row as one line: 'Header: value; Header: value'. Empty cells are skipped; a missing or blank
    header becomes 'Column N' (1-based)."""
    parts = []
    for i, value in enumerate(values):
        text = cell_text(value)
        if not text:
            continue
        header = normalize(headers[i]) if i < len(headers) else ""
        parts.append(f"{header or f'Column {i + 1}'}: {text}")
    return "; ".join(parts)

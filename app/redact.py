"""Redact (spec 9): personal data and secrets out of uploaded text, before storage and before any model call.
Regexes find secrets, emails, phone numbers and street addresses. Presidio (spaCy's small English model) finds
personal names, kept only when they look like one: two or more capitalised words and no organisation or
product word (the small model also tags company and product names as people; Plan 2 planning measured it on
the dev pack). Place names and cloud regions are kept on purpose: data-residency answers depend on them.
Sample packs are not redacted (Plan 1A Ruling 10); uploads and the visitor's own answers are."""

import re
import threading
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.contracts import Line

SCORE_THRESHOLD = 0.5
_SPACY_IGNORED = [  # spaCy labels with no Presidio entity: silences a warning per match
    "CARDINAL",
    "DATE",
    "EVENT",
    "FAC",
    "GPE",
    "LANGUAGE",
    "LAW",
    "LOC",
    "MONEY",
    "NORP",
    "ORDINAL",
    "ORG",
    "PERCENT",
    "PRODUCT",
    "QUANTITY",
    "TIME",
    "WORK_OF_ART",
]
_NOT_A_NAME = {
    "inc",
    "llc",
    "ltd",
    "corp",
    "company",
    "group",
    "security",
    "ledger",
    "workspace",
    "cloud",
    "console",
    "platform",
    "suite",
    "services",
    "service",
    "systems",
    "system",
    "software",
    "labs",
    "bank",
    "agreement",
    "policy",
    "plan",
    "report",
    "team",
    "office",
    "learning",
    "personnel",
    "management",
    "description",
}
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "SECRET",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    ),
    (
        "SECRET",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@]+@\S+", re.IGNORECASE),
    ),  # credentials in a URL
    ("SECRET", re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")),  # JSON web token
    (
        "SECRET",
        re.compile(
            r"\b(?:sk|pk|rk)[-_](?:(?:live|test)_)?[A-Za-z0-9_-]{16,}|\bgithub_pat_\w{20,}|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b"
            r"|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAIza[\w-]{35}\b|\bglpat-[\w-]{20,}"
            r"|\bBearer\s+[\w.~+/-]{16,}=*|(?:https?://)?\bhooks\.slack\.com/services/\S+|\bsig=[\w%]{16,}"
        ),
    ),
    (
        "SECRET",
        re.compile(  # an underscore or hyphen is a separator: DB_PASSWORD=, aws_secret_access_key =
            r"(?<![A-Za-z0-9])[\w-]*(?:api[_-]?key|secret|token|password|passwd|pwd)"
            r"(?:[_-][\w-]*(?:key|id|secret|token|value)|(?-i:[A-Z])\w*)?\s*[:=]\s*\S{8,}",
            re.IGNORECASE,
        ),
    ),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    (
        "PHONE",
        re.compile(r"(?<![\w+])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,4}(?!\w)"),
    ),
    (
        "ADDRESS",
        re.compile(
            r"\b\d{1,6}(?: [A-Z][a-z]+){1,4} (?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr"
            r"|Way|Court|Ct|Place|Pl|Parkway|Pkwy|Highway|Hwy)\b\.?(?:,? (?:Suite|Ste|Unit|Floor) \w+)?"
        ),
    ),
)
_analyzer: Any = None
_lock = threading.Lock()


def _engine() -> Any:
    """Presidio on spaCy's small model, built once on first use (uploads only; samples never load it)."""
    global _analyzer
    with _lock:
        if _analyzer is None:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            nlp = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                    "ner_model_configuration": {"labels_to_ignore": _SPACY_IGNORED},
                }
            ).create_engine()
            _analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
        return _analyzer


def _is_name_word(word: str) -> bool:
    """Capitalised (Unicode letters, hyphen or apostrophe parts), or ALL CAPS."""
    parts = re.split(r"[-']", word)
    if not all(p.isalpha() for p in parts):
        return False
    return word.isupper() or all(p[0].isupper() and p[1:] == p[1:].lower() for p in parts)


def _looks_like_a_name(span: str) -> bool:
    """Two or more words, each capitalised or ALL CAPS (DANA ORTIZ), a middle initial (Dana M. Ortiz) allowed,
    at least two of them real words, none an organisation or product word. Single names stay a known gap."""
    words = [w.strip(",.") for w in span.split()]
    full = [w for w in words if len(w) > 1]
    return (
        len(words) >= 2
        and len(full) >= 2
        and all(_is_name_word(w) for w in words)
        and not {w.lower() for w in words} & _NOT_A_NAME
    )


def spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, label) of everything to redact, left to right, never overlapping."""
    found = [(m.start(), m.end(), label) for label, rx in _PATTERNS for m in rx.finditer(text)]
    # Presidio's EmailRecognizer would fetch the Public Suffix List over HTTP; emails are the regex above.
    for r in _engine().analyze(text, language="en", entities=["PERSON"], score_threshold=SCORE_THRESHOLD):
        if _looks_like_a_name(text[r.start : r.end]):
            found.append((r.start, r.end, "PERSON"))
    kept: list[tuple[int, int, str]] = []
    for start, end, label in sorted(found, key=lambda s: (s[0], -s[1])):
        if not kept or start >= kept[-1][1]:
            kept.append((start, end, label))
    return kept


def redact_text(text: str) -> str:
    """Each span becomes <LABEL>: <PERSON>, <EMAIL>, <PHONE>, <ADDRESS> or <SECRET>. These never look like the
    [bracketed] placeholders that app/patterns.py flags."""
    for start, end, label in reversed(spans(text)):
        text = f"{text[:start]}<{label}>{text[end:]}"
    return text


def redact_lines(lines: Sequence[Line]) -> tuple[Line, ...]:
    return tuple(replace(line, text=redact_text(line.text)) for line in lines)

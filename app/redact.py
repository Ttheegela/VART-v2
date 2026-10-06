"""Redact (spec 9): personal data and secrets out of uploaded text, before storage and before any model call.
Regexes find secrets, emails, phone numbers and street addresses. Presidio (spaCy's small English model) finds
personal names, kept only when they look like one: two or more capitalised words and no organisation or
product word (the small model also tags company and product names as people; Plan 2 planning measured it on
the dev pack). Place names and cloud regions are kept on purpose: data-residency answers depend on them.
Sample packs are not redacted (Plan 1A Ruling 10); uploads and the visitor's own answers are."""

import os
import re
import threading
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.contracts import Line
from app.ingest.parse import IngestError

SCORE_THRESHOLD = 0.5
# spaCy costs up to ~3 s per crafted 20,000-character line (adversary checkpoint 3, I6): stop well inside the
# function's 300 s. Checked between slices, so the worst overrun is one slice (8 such lines, ~24 s).
DEADLINE_S = 120.0
SLICE = 8
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
_KW = r"(?:api[_-]?key|secret|token|passphrase|password|passwd|pwd)"
_QUOTED = r"(?:\"[^\"\n]{8,200}\"|'[^'\n]{8,200}')"
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "SECRET",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    ),
    (  # a PEM body row on its own line (docx, xlsx and csv give one line per row): a run of 40+ base64
        # characters with both cases, not touching a word, dot, colon, hyphen or percent (an '=' before it is
        # allowed: PRIVATE_KEY=MIIE...). A hex hash or base32 is single-case, an English word is never 40
        # letters, and a URL path touches a dot or colon. Over-redacts a bare base64 digest or a 40+ character
        # camelCase identifier, neither of which is evidence.
        "SECRET",
        re.compile(
            r"(?<![\w+/.:%-])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[A-Z])[A-Za-z0-9+/]{40,}={0,2}(?![\w+/=.:%-])"
        ),
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
            # start at a word start and bound every [\w-] run: linear time, not cubic, on a crafted line;
            # the value must mix letters and digits (Password: Required; Secret: HashiCorp Vault and
            # token_count: 1000000000 are evidence) and not end in a hyphenated word (Token: RS256-signed);
            # lookaheads are bounded so a failed start costs at most 200 characters
            r"(?<![\w-])[\w-]{0,64}(?:api[_-]?key|secret|token|password|passwd|pwd)"
            r"(?:[_-][\w-]{0,64}|(?-i:[A-Z])\w{0,64})?\s*[:=]\s*"
            r"(?=[^\s\d]{0,200}\d)(?=[^\sa-z]{0,200}[a-z])(?![^\s-]{0,200}-[a-z]{3,}\b)\S{8,}",
            re.IGNORECASE,
        ),
    ),
    (  # a key that ends in the secret word: bare (password), compound (DB_PASSWORD, client-secret,
        # db.password) or camelCase (clientSecret). '=' (env, ini, properties) or a quoted value is config, so
        # any 8+ characters count. After ':' only values a policy cell never holds: 8+ digits, or a passphrase
        # (12+ lowercase letters, or 4+ hyphen-joined lowercase words) that ends the value (re-review N1).
        "SECRET",
        re.compile(
            r"(?<![\w.-])(?:[\w.-]{0,64}[_.-]" + _KW + r"|[a-z][a-z0-9]{0,63}"
            r"(?-i:ApiKey|Secret|Token|Passphrase|Password|Passwd|Pwd)|" + _KW + r")"
            r"\s*(?:=\s*(?:"
            + _QUOTED
            + r"|\S{8,})|:\s*(?:"
            + _QUOTED
            + r"|\d{8,}(?![\w-])|(?-i:[a-z]{12,}|[a-z]+(?:-[a-z]+){3,})(?=\s*(?:[;,.]|$))))",
            re.IGNORECASE,
        ),
    ),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    (
        "PHONE",
        re.compile(  # not inside an IP address or CIDR, not a run of years, not a thousands-grouped number
            r"(?<![\w+])(?<!\d\.)(?!(?:(?:19|20)\d\d[ .-]){2}(?:19|20)\d\d(?!\w))"
            r"(?!\d{1,3}(?:[ .]\d{3}){2,}(?![\w.]))"
            r"(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,4}(?!\w|\.\d|/\d)"
        ),
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


def _person_results(texts: list[str]) -> list[list[Any]]:
    """Presidio's PERSON results per text, analysed in one batch (spaCy pipe): the same spans as one call per
    text, and faster. Never join the texts: that changes the spans."""
    from presidio_analyzer import BatchAnalyzerEngine

    batch = BatchAnalyzerEngine(_engine())
    return batch.analyze_iterator(
        texts, language="en", batch_size=64, entities=["PERSON"], score_threshold=SCORE_THRESHOLD
    )


_DIGIT_LEAD = re.compile(r"(?:\d+\s+)+")
_DIGIT_TAIL = re.compile(r"(?:\s+\d+)+$")


def _trim_digits(text: str, start: int, end: int) -> tuple[int, int]:
    """Digit tokens at a span's edge are not part of a name ("Marcus Lee 2026", preflight P2)."""
    span = text[start:end]
    lead = _DIGIT_LEAD.match(span)
    tail = _DIGIT_TAIL.search(span)
    return start + (lead.end() if lead else 0), end - (len(tail.group()) if tail else 0)


def _person_spans(text: str, people: list[Any]) -> list[tuple[int, int]]:
    """Presidio's PERSON ranges that read as a name. A pair joined only by ", " ("Ortiz, Dana") is tried as
    one name unless it sits in a longer comma list; when that fails, each span stands alone
    (preflight P15; triage row 30)."""
    groups: list[list[tuple[int, int]]] = []
    for start, end in sorted((r.start, r.end) for r in people):
        if groups and text[groups[-1][-1][1] : start] == ", ":
            groups[-1].append((start, end))
        else:
            groups.append([(start, end)])
    out: list[tuple[int, int]] = []
    for group in groups:
        first, last = group[0][0], group[-1][1]
        in_a_list = text[:first].endswith(", ")
        # a pair that follows a comma ("Okta, Duo, Ping") is a list of products, not "Last, First"; a pair
        # that starts the list and is followed by a title or more ("Kim, Sarah, CISO") still is
        for option in ([(first, last)], group) if len(group) == 2 and not in_a_list else (group,):
            trimmed = [_trim_digits(text, a, b) for a, b in option]
            kept = [t for t in trimmed if _looks_like_a_name(text[t[0] : t[1]])]
            if len(kept) == len(trimmed) or option is group:
                out += kept
                break
    return out


def _spans(text: str, people: list[Any]) -> list[tuple[int, int, str]]:
    found = [(m.start(), m.end(), label) for label, rx in _PATTERNS for m in rx.finditer(text)]
    # Presidio's EmailRecognizer would fetch the Public Suffix List over HTTP; emails are the regex above.
    found += [(start, end, "PERSON") for start, end in _person_spans(text, people)]
    kept: list[tuple[int, int, str]] = []
    for start, end, label in sorted(found, key=lambda s: (s[0], -s[1])):
        if not kept or start >= kept[-1][1]:
            kept.append((start, end, label))
    return kept


def spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, label) of everything to redact, left to right, never overlapping."""
    return _spans(
        text, _engine().analyze(text, language="en", entities=["PERSON"], score_threshold=SCORE_THRESHOLD)
    )


def _apply(text: str, found: list[tuple[int, int, str]]) -> str:
    for start, end, label in reversed(found):
        text = f"{text[:start]}<{label}>{text[end:]}"
    return text


def redact_text(text: str) -> str:
    """Each span becomes <LABEL>: <PERSON>, <EMAIL>, <PHONE>, <ADDRESS> or <SECRET>. These never look like the
    [bracketed] placeholders that app/patterns.py flags."""
    return _apply(text, spans(text))


_FILE_CONTEXT = "Notes from "


def _suffix_spans(root: str) -> list[tuple[int, int, str]]:
    """Regex spans of every part of the root bounded by separators (or its ends) on both sides: "\\b" treats
    "_" as a word character, so "notes_ghp_..._v2" hides a key from the patterns at either end (re-review
    I-B, I-1). Cheap: a file name is at most 255 characters (0.12 s worst case)."""
    seps = [m.start() for m in re.finditer(r"[_\W]", root)]
    starts = [0] + [i + 1 for i in seps]
    ends = seps + [len(root)]
    return [
        (a + i, b + i, label) for i in starts for e in ends if e > i for a, b, label in _spans(root[i:e], [])
    ]


def redact_filename(filename: str) -> str:
    """A file name's root read as words inside a sentence, where Presidio finds a bare name it misses alone
    ("Dana Ortiz.docx", triage row 31). Secrets, emails and the like are found on the original root and on
    each part after a separator; names on a copy whose separator runs are one space, with an index map back,
    so the original separators stay ("notes_from_<PERSON>_2026.md"). The extension is split off first.
    A lower-case name ("dana_ortiz.md") stays a known gap, like a single word."""
    root, ext = os.path.splitext(filename)
    idx: list[int] = []
    chars: list[str] = []
    for i, ch in enumerate(root):
        if re.match(r"[_\W]", ch):
            if chars and chars[-1] != " ":
                chars.append(" ")
                idx.append(i)
        else:
            chars.append(ch)
            idx.append(i)
    words = "".join(chars)
    sentence = f"{_FILE_CONTEXT}{words}."
    offset = len(_FILE_CONTEXT)
    found = _suffix_spans(root) + [
        (idx[a - offset], idx[b - offset - 1] + 1, label)
        for a, b, label in spans(sentence)
        if label == "PERSON" and a >= offset and b <= offset + len(words)
    ]
    kept: list[tuple[int, int, str]] = []
    for start, end, label in sorted(found, key=lambda s: (s[0], -s[1])):
        if kept and start < kept[-1][1]:  # overlap: one span, so an email glued to a name loses both
            kept[-1] = (kept[-1][0], max(end, kept[-1][1]), kept[-1][2])
        else:
            kept.append((start, end, label))
    return _apply(root, kept) + ext


def redact_lines(lines: Sequence[Line]) -> tuple[Line, ...]:
    """Raises IngestError when the lines take longer than DEADLINE_S (a crafted file, not a real document)."""
    deadline = time.monotonic() + DEADLINE_S
    out: list[Line] = []
    for start in range(0, len(lines), SLICE):
        if time.monotonic() > deadline:
            raise IngestError("This file takes too long to process; split it and upload the parts.")
        part = lines[start : start + SLICE]
        people = _person_results([line.text for line in part])
        out += [
            replace(line, text=_apply(line.text, _spans(line.text, found)))
            for line, found in zip(part, people, strict=True)
        ]
    return tuple(out)

"""Retrieve (spec 6.5): Postgres full-text candidates, ranked two ways (ts_rank_cd cover density and an
IDF-weighted overlap of the query's terms), merged by reciprocal rank fusion, at most two text passages and
three record rows per document, then extended by a record hop. Injection-flagged passages are removed here,
before any model call, and reported as dropped. No answer-key evidence is ever added."""

import math
import re
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.contracts import DocInfo, Dropped, Passage, Retrieval
from app.text import contains

K = 8  # passages per item (spec 6.6)
TEXT_CAP, RECORD_CAP = 2, 3  # per document; a record row is a one-line passage, so rows get their own cap
HOP = 3  # record rows the hop may add
HOP_MAX_CHUNKS = 5  # an identifier found in more chunks than this is too common to hop on (a company name)
RRF_K = 60
CANDIDATES = 200
MAX_QUERY_WORDS = 64  # distinct words of question and topic; the dev pack's longest cell has 22
# Security acronyms and their spelled-out forms; a query gets both. Generic domain words, not dev-pack tuning.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "mfa": ("multi-factor",),
    "multi-factor": ("mfa",),
    "2fa": ("multi-factor",),
    "sso": ("single sign-on",),
    "pentest": ("penetration test",),
    "sast": ("static analysis",),
    "dast": ("dynamic application security testing",),
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.'-]*[A-Za-z0-9]|[A-Za-z0-9]")
_FIRST_VALUE = re.compile(r"[^:;]+: ([^;]+)")
_COLUMNS = """c.id, c.document_id, c.line_start, c.text, c.heading, c.flags, c.as_of, c.record,
    d.filename, d.kind, d.status, d.effective_date, d.scope, d.evidence_allowed"""
_CANDIDATES = text(
    f"""SELECT {_COLUMNS}, tsvector_to_array(c.tsv) AS lexemes, length(c.tsv) AS size,
        round(ts_rank_cd(c.tsv, q.query, 1)::numeric, 6) AS cd
    FROM chunks c JOIN documents d ON d.id = c.document_id
    CROSS JOIN websearch_to_tsquery('english', :q) AS q(query)
    WHERE c.workspace_id = :ws AND c.tsv @@ q.query
    ORDER BY cd DESC, d.filename, c.line_start
    LIMIT :limit"""
)
_RECORDS = text(
    f"""SELECT {_COLUMNS} FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.workspace_id = :ws AND c.record ORDER BY d.filename, c.line_start"""
)
_DOCUMENT = text(
    f"""SELECT {_COLUMNS} FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.workspace_id = :ws AND c.document_id = :doc ORDER BY c.line_start"""
)


def build_query(question: str, topic: str | None) -> str:
    """The question's and topic's distinct words, at most MAX_QUERY_WORDS, OR-ed (websearch_to_tsquery would
    AND them), plus synonyms. Repeats change no rank (ts_rank_cd counts an operand once) but cost the database
    memory per operand, so one long cell could fail the item (adversary checkpoint 3, I2)."""
    words = list(dict.fromkeys(_WORD.findall(f"{question} {topic or ''}")))[:MAX_QUERY_WORDS]
    words += [s for w in words for s in SYNONYMS.get(w.lower(), ())]
    return " or ".join(f'"{w}"' if " " in w else w for w in words)


def _passage(row: Any) -> Passage:
    doc = DocInfo(
        str(row.document_id),
        row.filename,
        row.kind,
        row.status,
        row.effective_date,
        row.scope,
        row.evidence_allowed,
    )
    lines = tuple(row.text.split("\n"))  # a chunk's text is its lines joined with "\n" (app/chunk.py)
    return Passage(
        str(row.id), doc, row.line_start, lines, row.heading, tuple(row.flags), row.as_of, row.record
    )


def _fused(session: Session, workspace_id: uuid.UUID, query: str, rows: Sequence[Any]) -> list[Any]:
    """Reciprocal rank fusion of the cover-density order and an IDF-weighted order of the same candidates.
    IDF comes from ts_stat over this workspace, so a term found in few chunks counts for more."""
    inner = f"SELECT tsv FROM chunks WHERE workspace_id = '{uuid.UUID(str(workspace_id))}'"
    ndoc: dict[str, int] = {
        w: n for w, n in session.execute(text("SELECT word, ndoc FROM ts_stat(:inner)"), {"inner": inner})
    }
    total = (
        session.scalar(text("SELECT count(*) FROM chunks WHERE workspace_id = :ws"), {"ws": workspace_id})
        or 1
    )
    terms = set(
        session.scalar(
            text("SELECT coalesce(array_agg(lexeme), '{}') FROM unnest(to_tsvector('english', :q))"),
            {"q": query.replace('"', " ")},
        )
        or ()
    )

    def idf(row: Any) -> float:
        matched = terms.intersection(row.lexemes)
        score = sum(math.log(total / ndoc[w]) for w in matched if ndoc.get(w))
        return round(score / (1 + math.log(1 + row.size)), 9)

    by_idf = sorted(rows, key=lambda r: (-idf(r), r.filename, r.line_start))
    score: dict[Any, float] = {}
    for ranking in (rows, by_idf):
        for rank, row in enumerate(ranking):
            score[row.id] = score.get(row.id, 0.0) + 1 / (RRF_K + rank + 1)
    return sorted(rows, key=lambda r: (-round(score[r.id], 9), r.filename, r.line_start))


_CHUNKS_NAMING = text(
    """SELECT i, (SELECT count(*) FROM chunks c
        WHERE c.workspace_id = :ws AND strpos(lower(c.text), lower(i)) > 0)
    FROM unnest(CAST(:ids AS text[])) AS i"""
)


def _chunks_naming(session: Session, workspace_id: uuid.UUID, identifiers: set[str]) -> dict[str, int]:
    """How many of the workspace's chunks name each identifier, in one query."""
    rows = session.execute(_CHUNKS_NAMING, {"ws": workspace_id, "ids": sorted(identifiers)})
    return {i: int(n) for i, n in rows}


def _hop(session: Session, workspace_id: uuid.UUID, chosen: Sequence[Any]) -> list[Any]:
    """Record hop: record rows whose identifier (the row's first value: a system, asset or host name) is named
    in a selected passage and in at most HOP_MAX_CHUNKS chunks; rows of already-selected documents first.
    A row flagged injection is never added: it would reach the model (spec 6.5)."""
    named = "\n".join(r.text for r in chosen)
    have = {r.id for r in chosen}
    docs = {r.document_id for r in chosen}
    named_rows = []
    for row in session.execute(_RECORDS, {"ws": workspace_id}):
        # ponytail: reads the first "Header: value" back out of a record line (app/text.py says lines are for
        # reading, not parsing); a value holding "; " only costs a missed or extra hop, never a citation.
        first = _FIRST_VALUE.match(row.text)
        if row.id in have or first is None or "injection" in row.flags:
            continue
        identifier = first.group(1).strip()
        if contains(named, identifier):
            named_rows.append((row, identifier))
    # One count per distinct identifier, all in one query: a count per row made the hop rows x chunks
    # (adversary checkpoint 3, I1). Identifiers are bounded by the words of the chosen passages.
    counts = _chunks_naming(session, workspace_id, {i for _, i in named_rows}) if named_rows else {}
    found = [row for row, i in named_rows if counts[i] <= HOP_MAX_CHUNKS]
    found.sort(key=lambda r: r.document_id not in docs)  # stable: filename and line order inside each group
    return found[:HOP]


def retrieve(session: Session, workspace_id: uuid.UUID, question: str, topic: str | None) -> Retrieval:
    """At most K passages for one questionnaire item, best first."""
    query = build_query(question, topic)
    rows = session.execute(_CANDIDATES, {"q": query, "ws": workspace_id, "limit": CANDIDATES}).all()
    if not rows:
        return Retrieval((), ())
    ranked = _fused(session, workspace_id, query, rows)
    dropped = tuple(
        Dropped(str(r.id), str(r.document_id), r.filename, "injection")
        for r in ranked[:K]
        if "injection" in r.flags
    )
    clean = [r for r in ranked if "injection" not in r.flags]
    chosen: list[Any] = []
    per_doc: dict[tuple[Any, bool], int] = {}

    def take(limit: int) -> None:
        have = {r.id for r in chosen}
        for row in clean:
            if len(chosen) >= limit:
                return
            key = (row.document_id, row.record)
            if row.id not in have and per_doc.get(key, 0) < (RECORD_CAP if row.record else TEXT_CAP):
                chosen.append(row)
                have.add(row.id)
                per_doc[key] = per_doc.get(key, 0) + 1

    take(K - HOP)
    chosen.extend(_hop(session, workspace_id, chosen))
    take(K)
    return Retrieval(tuple(_passage(r) for r in chosen), dropped)


def document_passages(
    session: Session, workspace_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[Passage, ...]:
    """Every chunk of one document as passages (the interview re-check reads a statement this way)."""
    rows = session.execute(_DOCUMENT, {"ws": workspace_id, "doc": document_id})
    return tuple(_passage(r) for r in rows)

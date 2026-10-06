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
from app.text import contains, normalize

K = 8  # passages per item (spec 6.6)
TEXT_CAP, RECORD_CAP = 2, 3  # per document; a record row is a one-line passage, so rows get their own cap
HOP = 3  # record rows the hop may add
HOP_MAX_CHUNKS = 5  # an identifier found in more chunks than this is too common to hop on (a company name)
RRF_K = 60
CANDIDATES = 200
MAX_QUERY_CHARS = 2000  # question and topic, cut before tokenising; the dev pack's longest cell has 154
# Named identifiers the hop looks at per item; the dev pack's record rows hold about 20: never binds.
HOP_MAX_IDENTIFIERS = 32
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
    # People leaving: questionnaires say leaver or offboarding, audit reports say termination. One direction
    # only: "termination" is also a contract's end, which is not an employee leaving.
    **{w: ("terminated", "termination") for w in ("leaver", "leavers", "departure", "offboarding")},
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
    WHERE c.workspace_id = :ws AND c.tsv @@ q.query AND NOT d.kind = ANY(CAST(:exclude AS text[]))
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
    AND them), plus the joined form of hyphenated words and synonyms. Repeats change no rank
    (ts_rank_cd counts an operand once) but cost the database memory per operand, so one long cell could fail
    the item (adversary checkpoint 3, I2)."""
    source = f"{question} {topic or ''}"[:MAX_QUERY_CHARS]  # one hyphenated word parses into many operands
    words = list(dict.fromkeys(_WORD.findall(source)))[:MAX_QUERY_WORDS]
    # "re-certification" also searches "recertification" (the parser keeps the parts). No spaced form: with a
    # stopword part it collapses to one common word ("up-to-date" -> date).
    words += [w.replace("-", "") for w in words if "-" in w]
    words += [s for w in words for s in SYNONYMS.get(w.lower().removesuffix("'s"), ())]
    words = list(dict.fromkeys(words))
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


def _chunks_naming(session: Session, workspace_id: uuid.UUID, identifier: str) -> int:
    count = session.scalar(
        text("SELECT count(*) FROM chunks WHERE workspace_id = :ws AND strpos(lower(text), lower(:i)) > 0"),
        {"ws": workspace_id, "i": identifier},
    )
    return int(count or 0)


def _hop(session: Session, workspace_id: uuid.UUID, chosen: Sequence[Any]) -> list[Any]:
    """Record hop: record rows whose identifier (the row's first value: a system, asset or host name) is named
    in a selected passage and in at most HOP_MAX_CHUNKS chunks; rows of already-selected documents first.
    A row flagged injection is never added: it would reach the model (spec 6.5)."""
    named = "\n".join(r.text for r in chosen)
    have = {r.id for r in chosen}
    docs = {r.document_id for r in chosen}
    rows = []
    for row in session.execute(_RECORDS, {"ws": workspace_id}):
        # ponytail: reads the first "Header: value" back out of a record line (app/text.py says lines are for
        # reading, not parsing); a value holding "; " only costs a missed or extra hop, never a citation.
        first = _FIRST_VALUE.match(row.text)
        if row.id not in have and first is not None and "injection" not in row.flags:
            rows.append((row, first.group(1).strip()))
    # Walk the rows in the hop's final order (rows of selected documents first; stable, so filename and line
    # order inside each group) and stop at HOP rows. A chosen record row can be 20,000 characters naming
    # thousands of systems, so looking at every named identifier was identifiers x chunks (adversary
    # checkpoint 3, I1 and N1): each named identifier is looked at once, and at most HOP_MAX_IDENTIFIERS.
    rows.sort(key=lambda p: p[0].document_id not in docs)
    plain = normalize(named)  # contains' own first test, done once here instead of once per row
    hops: dict[str, bool] = {}
    found: list[Any] = []
    for row, identifier in rows:
        if len(found) == HOP:
            break
        if identifier not in hops:
            needle = normalize(identifier)
            if not needle or needle not in plain:
                continue  # not named: contains would say False
            if len(hops) == HOP_MAX_IDENTIFIERS:
                break  # ponytail: a later row might have hopped; raise the cap if real inventories need it
            hops[identifier] = (
                contains(named, identifier)
                and _chunks_naming(session, workspace_id, identifier) <= HOP_MAX_CHUNKS
            )
        if hops[identifier]:
            found.append(row)
    return found


def retrieve(
    session: Session,
    workspace_id: uuid.UUID,
    question: str,
    topic: str | None,
    exclude_kinds: Sequence[str] = (),
) -> Retrieval:
    """At most K passages for one questionnaire item, best first. Documents of `exclude_kinds` are never
    candidates, so they take no slot (Plan 6B: a Checked CSF part is judged without statements)."""
    query = build_query(question, topic)
    params = {"q": query, "ws": workspace_id, "limit": CANDIDATES, "exclude": list(exclude_kinds)}
    rows = session.execute(_CANDIDATES, params).all()
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

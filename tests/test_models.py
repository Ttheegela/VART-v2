from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Chunk, Document, DocumentLine, Workspace
from tests import factories as f


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _run(s: Session):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    q = f.questionnaire(s, ws)
    return ws, q, f.item(s, q), f.run(s, q)


def test_verified_answer_with_a_citation_is_accepted(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it, label="verified", value="Yes", citations=[f.CITATION], confidence=0.9)
    s.commit()


@pytest.mark.parametrize("label", ["verified", "partial"])
def test_verified_or_partial_answer_needs_a_citation(s: Session, label: str) -> None:
    _, _, it, r = _run(s)
    with pytest.raises(IntegrityError, match="ck_answers_cited"):
        f.answer(s, r, it, label=label, value="Yes", citations=[])


def test_unknown_answer_needs_no_citation(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it, label="unknown")
    s.commit()


def test_user_confirmed_answer_needs_its_statement(s: Session) -> None:
    ws, _, it, r = _run(s)
    with pytest.raises(IntegrityError, match="ck_answers_statement"):
        f.answer(s, r, it, label="user_confirmed")
    s.rollback()
    ws, _, it, r = _run(s)
    stmt = f.document(s, ws, kind="statement", source="statement", filename="answer.txt")
    f.answer(s, r, it, label="user_confirmed", statement_id=stmt.id)
    s.commit()


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"label": "maybe"}, "ck_answers_label"),
        ({"label": "unknown", "value": "Maybe"}, "ck_answers_value"),
        ({"label": "unknown", "confidence": 1.5}, "ck_answers_confidence"),
    ],
)
def test_answer_fields_are_constrained(s: Session, fields: dict[str, object], constraint: str) -> None:
    _, _, it, r = _run(s)
    with pytest.raises(IntegrityError, match=constraint):
        f.answer(s, r, it, **fields)


def test_one_answer_per_item_per_run(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it)
    with pytest.raises(IntegrityError, match="uq_answers_run_item"):
        f.answer(s, r, it)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"flags": ["shouting"]}, "ck_chunks_flags"),
        ({"line_start": 3, "line_end": 2}, "ck_chunks_lines"),
        ({"line_start": 0, "line_end": 0}, "ck_chunks_lines"),
    ],
)
def test_chunk_fields_are_constrained(s: Session, fields: dict[str, object], constraint: str) -> None:
    doc = f.document(s, f.workspace(s))
    with pytest.raises(IntegrityError, match=constraint):
        f.chunk(s, doc, **fields)


def test_document_kind_is_constrained(s: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_documents_kind"):
        f.document(s, f.workspace(s), kind="memo")


def test_chunks_are_full_text_searchable(s: Session) -> None:
    doc = f.document(s, f.workspace(s))
    f.chunk(s, doc, heading="Access reviews", text="User access is reviewed quarterly.", flags=["negation"])
    s.commit()
    hits = s.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.tsv.op("@@")(func.websearch_to_tsquery("english", "quarterly access review")))
    )
    assert hits == 1


def test_deleting_a_workspace_deletes_everything_in_it(s: Session) -> None:
    ws, _, it, r = _run(s)
    doc = f.document(s, ws)
    s.add(DocumentLine(document_id=doc.id, n=1, text="Access is reviewed quarterly."))
    f.chunk(s, doc)
    stmt = f.document(s, ws, kind="statement", source="statement", filename="answer.txt")
    f.answer(s, r, it, label="user_confirmed", statement_id=stmt.id)
    s.add(AuditEvent(workspace_id=ws.id, actor="visitor", action="upload"))
    s.commit()
    s.execute(delete(Workspace).where(Workspace.id == ws.id))
    s.commit()
    for table in (
        "documents",
        "document_lines",
        "chunks",
        "questionnaires",
        "items",
        "runs",
        "answers",
        "audit_events",
    ):
        assert s.scalar(text(f"select count(*) from {table}")) == 0, table
    assert s.scalar(select(func.count()).select_from(Document)) == 0

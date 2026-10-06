from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Answer,
    AuditEvent,
    Base,
    Chunk,
    Document,
    DocumentLine,
    LlmUsage,
    RunItem,
    SuggestedFill,
    Workspace,
)
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


def test_an_answer_without_a_conflict_stores_sql_null(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it, conflict=None)  # explicit None: SQL NULL, not the JSON value null
    s.commit()
    assert s.scalar(select(func.count()).select_from(Answer).where(Answer.conflict.is_(None))) == 1


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


def _add(s: Session, row: object) -> None:
    s.add(row)
    s.flush()


def _bad_run_item(s: Session) -> None:
    _, _, it, r = _run(s)
    _add(s, RunItem(run_id=r.id, item_id=it.id, state="stuck"))


def _bad_document_line(s: Session) -> None:
    _add(
        s,
        DocumentLine(document_id=f.document(s, f.workspace(s)).id, n=0, text="Access is reviewed quarterly."),
    )


def _second_item_at_position_1(s: Session) -> None:
    _, q, _, _ = _run(s)  # _run already put an item at position 1
    f.item(s, q, row_ref="Questionnaire!C7")


def _answer_with_json_object(s: Session, column: str) -> None:
    # label unknown on purpose: for verified or partial, ck_answers_cited would be evaluated first
    _, _, it, r = _run(s)
    f.answer(s, r, it, label="unknown", **{column: {}})


@pytest.mark.parametrize(
    ("constraint", "make"),
    [
        ("ck_documents_source", lambda s: f.document(s, f.workspace(s), source="email")),
        ("ck_documents_status", lambda s: f.document(s, f.workspace(s), status="bogus")),
        ("ck_documents_metadata_source", lambda s: f.document(s, f.workspace(s), metadata_source="llm")),
        ("ck_questionnaires_source", lambda s: f.questionnaire(s, f.workspace(s), source="email")),
        ("ck_runs_status", lambda s: f.run(s, f.questionnaire(s, f.workspace(s)), status="paused")),
        ("ck_run_items_state", _bad_run_item),
        ("ck_document_lines_n", _bad_document_line),
        ("uq_items_position", _second_item_at_position_1),
        ("ck_answers_json_arrays", lambda s: _answer_with_json_object(s, "citations")),
        ("ck_answers_json_arrays", lambda s: _answer_with_json_object(s, "dropped")),
    ],
)
def test_other_named_constraints_reject_bad_rows(
    s: Session, constraint: str, make: Callable[[Session], object]
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        make(s)


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
    s.add(RunItem(run_id=r.id, item_id=it.id))
    s.add(LlmUsage(workspace_id=ws.id, hour_start=datetime(2026, 1, 1, tzinfo=UTC), kind="draft", calls=1))
    f.question(s, r, it)
    f.suggestion(s, r, it, stmt)
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
        "run_items",
        "answers",
        "interview_questions",
        "suggestions",
        "audit_events",
        "llm_usage",
    ):
        assert s.scalar(text(f"select count(*) from {table}")) == 0, table
    assert s.scalar(select(func.count()).select_from(Document)) == 0


_CHECKS = text("""
    select c.relname, k.conname, pg_get_constraintdef(k.oid)
    from pg_constraint k join pg_class c on c.oid = k.conrelid join pg_namespace n on n.oid = c.relnamespace
    where k.contype = 'c' and n.nspname = :schema
""")


def test_migrated_check_constraints_match_the_models(migrated_db: Engine) -> None:
    """`alembic check` never compares CHECK constraints, and the tests above run against the migrated tables,
    so a rule edited only in models.py would pass CI and never reach production (nor the reverse). Postgres
    normalizes the definition on both sides. pg_attrdef is left out on purpose: sequence defaults print as
    nextval('public.x_id_seq') in one schema and nextval('x_id_seq') in the other; `alembic check` compares
    the other server defaults (compare_server_default in migrations/env.py)."""
    with migrated_db.begin() as conn:
        conn.execute(text("drop schema if exists model_probe cascade; create schema model_probe"))
        conn.execute(text("set local search_path to model_probe"))
        Base.metadata.create_all(conn)
        from_models = set(conn.execute(_CHECKS, {"schema": "model_probe"}).all())
        conn.execute(text("drop schema model_probe cascade"))
        migrated = set(conn.execute(_CHECKS, {"schema": "public"}).all())
    assert migrated, "no CHECK constraints found in the migrated schema"
    assert migrated == from_models, sorted(migrated ^ from_models)


def test_a_chunk_is_not_a_record_row_unless_marked(s: Session) -> None:
    ws = f.workspace(s)
    doc = f.document(s, ws)
    plain = f.chunk(s, doc)
    row = f.chunk(s, doc, line_start=2, line_end=2, text="System: Okta; Status: Overdue", record=True)
    s.commit()
    assert (plain.record, row.record) == (False, True)


def test_answer_keeps_what_decide_needs_to_run_again(s: Session) -> None:
    q = f.questionnaire(s, f.workspace(s))
    a = f.answer(s, f.run(s, q), f.item(s, q))
    s.refresh(a)
    assert (a.stances, a.chunk_ids, a.retrieval_dropped) == ([], [], [])


def test_a_question_is_asked_at_most_twice(s: Session) -> None:
    ws = f.workspace(s)
    q = f.questionnaire(s, ws)
    r = f.run(s, q)
    it = f.item(s, q)
    with pytest.raises(IntegrityError, match="ck_interview_questions_asked"):
        f.question(s, r, it, asked_count=3)


def test_one_question_per_item_set_per_run(s: Session) -> None:
    ws = f.workspace(s)
    q = f.questionnaire(s, ws)
    r = f.run(s, q)
    it = f.item(s, q)
    f.question(s, r, it)
    with pytest.raises(IntegrityError, match="uq_interview_questions_items"):
        f.question(s, r, it)


def test_a_suggestion_needs_a_citation_and_a_cited_label(s: Session) -> None:
    ws = f.workspace(s)
    q = f.questionnaire(s, ws)
    r = f.run(s, q)
    it = f.item(s, q)
    st = f.document(s, ws, source="statement", kind="statement")
    with pytest.raises(IntegrityError, match="ck_suggestions_cited"):
        f.suggestion(s, r, it, st, citations=[])
    s.rollback()
    with pytest.raises(IntegrityError, match="ck_suggestions_label"):
        f.suggestion(s, r, it, st, label="unknown")


def test_run_items_count_their_attempts(s: Session) -> None:
    ws = f.workspace(s)
    q = f.questionnaire(s, ws)
    r = f.run(s, q)
    ri = RunItem(run_id=r.id, item_id=f.item(s, q).id)
    s.add(ri)
    s.flush()
    s.refresh(ri)
    assert ri.attempts == 0


def test_a_questionnaire_may_be_the_built_in_csf_one(s: Session) -> None:
    q = f.questionnaire(s, f.workspace(s), source="csf", filename="csf-2.0", mapping={"scope": "core"})
    s.commit()
    assert (q.source, q.mapping) == ("csf", {"scope": "core"})


def test_a_fill_is_unique_per_part_of_an_item(db: Engine) -> None:
    with Session(db) as s:
        ws = f.workspace(s)
        q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
        it = f.item(s, q, csf_id="GV.PO-01", code="GV.PO-01", row_ref="GV.PO-01")
        r = f.run(s, q)
        st = f.document(s, ws, source="statement", kind="statement", filename="answer-001.txt")
        f.suggestion(s, r, it, st, part=1)
        f.suggestion(s, r, it, st, part=2)  # another part of the same outcome, from the same answer
        s.commit()
        with pytest.raises(IntegrityError, match="uq_suggestions_fill"):
            f.suggestion(s, r, it, st, part=2)
        s.rollback()
        with pytest.raises(IntegrityError, match="ck_suggestions_part"):
            f.suggestion(s, r, it, st, part=-1)


def test_run_item_parts_start_empty_and_must_be_an_object(db: Engine) -> None:
    with Session(db) as s:
        ws = f.workspace(s)
        q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
        it = f.item(s, q, csf_id="PR.DS-11", code="PR.DS-11", row_ref="PR.DS-11")
        r = f.run(s, q)
        ri = RunItem(run_id=r.id, item_id=it.id)
        s.add(ri)
        s.commit()
        s.refresh(ri)
        assert ri.parts == {}
        ri.parts = []  # type: ignore[assignment]
        with pytest.raises(IntegrityError, match="ck_run_items_parts"):
            s.commit()


BEFORE_PARTS = "a7c3e9d1b2f4"  # the revision before c4e8a2d6f1b3_csf_parts


def _csf_rows(s: Session, part: int) -> tuple[RunItem, SuggestedFill]:
    ws = f.workspace(s)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    it = f.item(s, q, csf_id="GV.PO-01", code="GV.PO-01", row_ref="GV.PO-01")
    r = f.run(s, q)
    st = f.document(s, ws, source="statement", kind="statement", filename="answer-001.txt")
    ri = RunItem(run_id=r.id, item_id=it.id, parts={"1": {"question": "q"}})
    s.add(ri)
    sg = f.suggestion(s, r, it, st, part=part)
    s.commit()
    return ri, sg


def test_the_parts_downgrade_refuses_while_a_fill_is_for_one_part(db: Engine) -> None:
    # Review I1: the narrower key could not hold two parts of one item, so the downgrade stops, schema intact.
    cfg = Config("alembic.ini")
    with Session(db) as s:
        _csf_rows(s, part=1)
    try:
        with pytest.raises(RuntimeError, match="1 suggestion"):
            command.downgrade(cfg, BEFORE_PARTS)
        with db.connect() as conn:
            assert conn.execute(text("select part from suggestions")).scalars().all() == [1]
    finally:
        command.upgrade(cfg, "head")


def test_the_parts_downgrade_runs_and_existing_rows_read_the_defaults_after_upgrade(db: Engine) -> None:
    cfg = Config("alembic.ini")
    with Session(db) as s:
        ri, sg = _csf_rows(s, part=0)
        ids = (ri.run_id, ri.item_id, sg.id)
    try:
        command.downgrade(cfg, BEFORE_PARTS)
        with db.connect() as conn:
            cols = conn.execute(
                text(
                    "select column_name from information_schema.columns "
                    "where (table_name, column_name) in (('run_items', 'parts'), ('suggestions', 'part'))"
                )
            ).all()
            assert cols == []
    finally:
        command.upgrade(cfg, "head")
    with Session(db) as s:
        ri2 = s.get_one(RunItem, (ids[0], ids[1]))
        assert ri2.parts == {}  # the row existed before the upgrade; it reads the server default
        assert s.get_one(SuggestedFill, ids[2]).part == 0

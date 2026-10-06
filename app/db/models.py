import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOC_KINDS = ("policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other")
LABELS = ("verified", "partial", "conflict", "unknown", "user_confirmed", "na")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = _created_at()
    ip_hash: Mapped[str | None] = mapped_column(String(32), default=None)
    __table_args__ = (Index("ix_workspaces_created_at", "created_at"),)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(8), default="final", server_default="final")
    effective_date: Mapped[date | None] = mapped_column(Date, default=None)
    scope: Mapped[str | None] = mapped_column(Text, default=None)
    evidence_allowed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    metadata_source: Mapped[str] = mapped_column(String(8), default="rule", server_default="rule")
    line_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        CheckConstraint(
            _in("source", ("sample", "upload", "drive", "statement")), name="ck_documents_source"
        ),
        CheckConstraint(_in("kind", DOC_KINDS), name="ck_documents_kind"),
        CheckConstraint(_in("status", ("final", "draft")), name="ck_documents_status"),
        CheckConstraint(
            _in("metadata_source", ("rule", "model", "user")), name="ck_documents_metadata_source"
        ),
    )


class DocumentLine(Base):
    __tablename__ = "document_lines"
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("n >= 1", name="ck_document_lines_n"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text, default=None)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    as_of: Mapped[date | None] = mapped_column(Date, default=None)
    # One spreadsheet or table row: decide asks its quotes for whole "Header: value" fields (adversary F10).
    record: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True),
    )
    __table_args__ = (
        CheckConstraint("line_start >= 1 AND line_end >= line_start", name="ck_chunks_lines"),
        CheckConstraint(
            "flags <@ ARRAY['negation', 'placeholder', 'injection']::text[]", name="ck_chunks_flags"
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))
    original_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True, default=None)
    sheet: Mapped[str | None] = mapped_column(String(255), default=None)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        CheckConstraint(_in("source", ("sample", "upload", "drive", "csf")), name="ck_questionnaires_source"),
    )


class Item(Base):
    __tablename__ = "items"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    # No index on questionnaire_id: uq_items_position (questionnaire_id, position) already leads with it.
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questionnaires.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    row_ref: Mapped[str] = mapped_column(String(64))
    code: Mapped[str | None] = mapped_column(String(64), default=None)
    topic: Mapped[str | None] = mapped_column(Text, default=None)
    question: Mapped[str] = mapped_column(Text)
    csf_id: Mapped[str | None] = mapped_column(String(16), default=None)
    __table_args__ = (UniqueConstraint("questionnaire_id", "position", name="uq_items_position"),)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questionnaires.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="running", server_default="running")
    prompt_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    models: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), server_default="0")
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    __table_args__ = (CheckConstraint(_in("status", ("running", "done", "failed")), name="ck_runs_status"),)


class RunItem(Base):
    __tablename__ = "run_items"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    # Indexed: deleting an item cascades here, and the primary key leads with run_id, not item_id.
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    state: Mapped[str] = mapped_column(String(8), default="pending", server_default="pending")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Claims so far; an item whose step crashed three times is answered as failed instead of claimed again.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # A CSF outcome's part results as they land (CSF spec 5.7):
    # {"1": {"question": ..., **runs._raw(...)}, ...}; a step refused mid-outcome resumes from here without
    # paying again. Empty for a questionnaire item.
    parts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    __table_args__ = (
        CheckConstraint(_in("state", ("pending", "claimed", "done")), name="ck_run_items_state"),
        CheckConstraint("jsonb_typeof(parts) = 'object'", name="ck_run_items_parts"),
        Index("ix_run_items_state", "run_id", "state"),
    )


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    # No index on run_id: uq_answers_run_item (run_id, item_id) already leads with it.
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    value: Mapped[str | None] = mapped_column(String(8), default=None)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    dropped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # none_as_null: an explicit None is SQL NULL, not JSON null, so "conflict IS NULL" finds plain answers.
    conflict: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), default=None)
    scope_note: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # NO ACTION: a statement that an answer cites cannot be deleted by itself. A workspace delete still works
    # because answers.workspace_id cascades at the first level, and Postgres checks this key (NO ACTION or
    # RESTRICT alike) only after the first-level cascades, by which time those answers are gone.
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), default=None, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # What decide needs to run again with no model call after a metadata override (spec 6.7;
    # docs/CONTRACTS.md "JSON shapes for Plan 3"): the stances, the passages' chunk ids in the order the
    # stances index them, and the retrieval drops (decide's third argument).
    stances: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    chunk_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    retrieval_dropped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        UniqueConstraint("run_id", "item_id", name="uq_answers_run_item"),
        CheckConstraint(_in("label", LABELS), name="ck_answers_label"),
        CheckConstraint("value IS NULL OR value IN ('Yes', 'No', 'Partial')", name="ck_answers_value"),
        CheckConstraint(
            "jsonb_typeof(citations) = 'array' AND jsonb_typeof(dropped) = 'array'",
            name="ck_answers_json_arrays",
        ),
        CheckConstraint(
            "label NOT IN ('verified', 'partial') OR jsonb_array_length(citations) > 0",
            name="ck_answers_cited",
        ),
        CheckConstraint("label <> 'user_confirmed' OR statement_id IS NOT NULL", name="ck_answers_statement"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_answers_confidence"),
        CheckConstraint(
            "jsonb_typeof(stances) = 'array' AND jsonb_typeof(chunk_ids) = 'array' "
            "AND jsonb_typeof(retrieval_dropped) = 'array'",
            name="ck_answers_engine_arrays",
        ),
    )


class InterviewQuestion(Base):
    """One entry of "Questions for you" (spec 5 step 6, 6.9). `rank` is the planner's order; asked at most
    twice: the question and its one follow-up."""

    __tablename__ = "interview_questions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    item_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    reason: Mapped[str] = mapped_column(String(8))
    rank: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open", server_default="open")
    asked_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    answer_text: Mapped[str | None] = mapped_column(Text, default=None)  # redacted
    statement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), default=None)
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        UniqueConstraint("run_id", "item_ids", name="uq_interview_questions_items"),
        CheckConstraint(
            _in("reason", ("conflict", "unknown", "partial")), name="ck_interview_questions_reason"
        ),
        CheckConstraint(
            _in("status", ("open", "follow_up", "answered", "skipped")), name="ck_interview_questions_status"
        ),
        CheckConstraint("asked_count BETWEEN 0 AND 2", name="ck_interview_questions_asked"),
        CheckConstraint("cardinality(item_ids) >= 1", name="ck_interview_questions_items"),
    )


class SuggestedFill(Base):
    """A fill the statement re-check found (spec 6.9): shown, never applied until the visitor accepts it."""

    __tablename__ = "suggestions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    # NO ACTION, as answers.statement_id: a statement a suggestion cites cannot be deleted by itself.
    statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    value: Mapped[str | None] = mapped_column(String(8), default=None)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    dropped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")
    part: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")  # CSF spec 5.6; 0: item
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        UniqueConstraint("run_id", "item_id", "statement_id", "part", name="uq_suggestions_fill"),
        CheckConstraint("part >= 0", name="ck_suggestions_part"),
        CheckConstraint(_in("label", ("verified", "partial")), name="ck_suggestions_label"),
        CheckConstraint("value IS NULL OR value IN ('Yes', 'No', 'Partial')", name="ck_suggestions_value"),
        CheckConstraint(
            "jsonb_typeof(citations) = 'array' AND jsonb_array_length(citations) > 0",
            name="ck_suggestions_cited",
        ),
        CheckConstraint(_in("status", ("open", "accepted", "dismissed")), name="ck_suggestions_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_suggestions_confidence"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    ref: Mapped[str | None] = mapped_column(String(64), default=None)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    at: Mapped[datetime] = _created_at()


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    hour_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class IpLimit(Base):
    __tablename__ = "ip_limits"
    ip_hash: Mapped[str] = mapped_column(String(32), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)


class CanaryRun(Base):
    __tablename__ = "canary_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

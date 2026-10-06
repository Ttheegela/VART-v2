"""plan3 interview and runner

Revision ID: 3a1f0c9e7b21
Revises: ffbf91b464dc
Create Date: 2026-10-06 09:00:00

Additive only: two new tables, three answer columns and one run_items column, all with constant defaults,
so Plan 2 code runs on the migrated schema and a rollback of the deploy needs no database step.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3a1f0c9e7b21"
down_revision: Union[str, Sequence[str], None] = "ffbf91b464dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARRAYS = "jsonb_typeof(stances) = 'array' AND jsonb_typeof(chunk_ids) = 'array' AND jsonb_typeof(retrieval_dropped) = 'array'"


def upgrade() -> None:
    for name in ("stances", "chunk_ids", "retrieval_dropped"):
        op.add_column(
            "answers",
            sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        )
    op.create_check_constraint("ck_answers_engine_arrays", "answers", ARRAYS)
    op.add_column("run_items", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("item_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("reason", sa.String(length=8), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="open", nullable=False),
        sa.Column("asked_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("statement_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("reason IN ('conflict', 'unknown', 'partial')", name="ck_interview_questions_reason"),
        sa.CheckConstraint(
            "status IN ('open', 'follow_up', 'answered', 'skipped')", name="ck_interview_questions_status"
        ),
        sa.CheckConstraint("asked_count BETWEEN 0 AND 2", name="ck_interview_questions_asked"),
        sa.CheckConstraint("cardinality(item_ids) >= 1", name="ck_interview_questions_items"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "item_ids", name="uq_interview_questions_items"),
    )
    op.create_index("ix_interview_questions_workspace_id", "interview_questions", ["workspace_id"])
    op.create_table(
        "suggestions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("statement_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(length=8), nullable=True),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dropped", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("label IN ('verified', 'partial')", name="ck_suggestions_label"),
        sa.CheckConstraint("value IS NULL OR value IN ('Yes', 'No', 'Partial')", name="ck_suggestions_value"),
        sa.CheckConstraint(
            "jsonb_typeof(citations) = 'array' AND jsonb_array_length(citations) > 0", name="ck_suggestions_cited"
        ),
        sa.CheckConstraint("status IN ('open', 'accepted', 'dismissed')", name="ck_suggestions_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_suggestions_confidence"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "item_id", "statement_id", name="uq_suggestions_fill"),
    )
    for column in ("workspace_id", "item_id", "statement_id"):
        op.create_index(f"ix_suggestions_{column}", "suggestions", [column])


def downgrade() -> None:
    op.drop_table("suggestions")
    op.drop_table("interview_questions")
    op.drop_column("run_items", "attempts")
    op.drop_constraint("ck_answers_engine_arrays", "answers", type_="check")
    for name in ("retrieval_dropped", "chunk_ids", "stances"):
        op.drop_column("answers", name)

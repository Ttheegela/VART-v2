"""csf parts: per-part results and per-part fills

Revision ID: c4e8a2d6f1b3
Revises: a7c3e9d1b2f4
Create Date: 2026-10-06 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4e8a2d6f1b3"
down_revision: Union[str, Sequence[str], None] = "a7c3e9d1b2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Plan 6B, additive (CSF spec 5.6-5.7): a CSF outcome's part results are stored as they land
    (run_items.parts, carry a), and a suggested fill names the part it is for (suggestions.part, 0 for a whole
    item, carry c). Existing rows get '{}' and 0. The code before 6B never reads either column, and its
    untargeted ON CONFLICT DO NOTHING works with the widened unique key."""
    op.add_column(
        "run_items",
        sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.create_check_constraint("ck_run_items_parts", "run_items", "jsonb_typeof(parts) = 'object'")
    op.add_column("suggestions", sa.Column("part", sa.SmallInteger(), server_default="0", nullable=False))
    op.create_check_constraint("ck_suggestions_part", "suggestions", "part >= 0")
    op.drop_constraint("uq_suggestions_fill", "suggestions", type_="unique")
    op.create_unique_constraint(
        "uq_suggestions_fill", "suggestions", ["run_id", "item_id", "statement_id", "part"]
    )


def downgrade() -> None:
    """Refuses while per-part fills exist: the narrower key could not hold two parts of one item."""
    parts = op.get_bind().exec_driver_sql("SELECT count(*) FROM suggestions WHERE part > 0").scalar()
    if parts:
        raise RuntimeError(f"{parts} suggestion(s) are for one part; delete them by hand before downgrading")
    op.drop_constraint("uq_suggestions_fill", "suggestions", type_="unique")
    op.create_unique_constraint("uq_suggestions_fill", "suggestions", ["run_id", "item_id", "statement_id"])
    op.drop_constraint("ck_suggestions_part", "suggestions", type_="check")
    op.drop_column("suggestions", "part")
    op.drop_constraint("ck_run_items_parts", "run_items", type_="check")
    op.drop_column("run_items", "parts")

"""runs stepped_at: when a step last touched a run

Revision ID: e7d1f3a5b9c2
Revises: c4e8a2d6f1b3
Create Date: 2026-10-07 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7d1f3a5b9c2"
down_revision: Union[str, Sequence[str], None] = "c4e8a2d6f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Plan 4, additive: a step records its time, so a run no step has touched for 10 minutes (a closed tab)
    blocks neither a new run nor a document delete. Existing rows read NULL (started_at stands in). The code
    before Plan 4 never reads the column."""
    op.add_column("runs", sa.Column("stepped_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "stepped_at")

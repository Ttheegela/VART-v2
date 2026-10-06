"""questionnaires csf source

Revision ID: a7c3e9d1b2f4
Revises: 3a1f0c9e7b21
Create Date: 2026-10-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d1b2f4"
down_revision: Union[str, Sequence[str], None] = "3a1f0c9e7b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The built-in CSF gap-check questionnaire (CSF spec 6). Additive: no existing row changes."""
    op.drop_constraint("ck_questionnaires_source", "questionnaires", type_="check")
    op.create_check_constraint(
        "ck_questionnaires_source", "questionnaires", "source IN ('sample', 'upload', 'drive', 'csf')"
    )


def downgrade() -> None:
    """Refuses while 'csf' rows exist: the old check would reject them and deleting them loses data."""
    csf_rows = op.get_bind().exec_driver_sql("SELECT count(*) FROM questionnaires WHERE source = 'csf'").scalar()
    if csf_rows:
        raise RuntimeError(f"{csf_rows} questionnaire(s) have source 'csf'; delete them by hand before downgrading")
    op.drop_constraint("ck_questionnaires_source", "questionnaires", type_="check")
    op.create_check_constraint(
        "ck_questionnaires_source", "questionnaires", "source IN ('sample', 'upload', 'drive')"
    )

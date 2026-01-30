"""refdata_updates

Revision ID: 20260130_02_refdata_updates
Revises: 20260130_01_visit_plan_lock
Create Date: 2026-01-30

"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260130_02_refdata_updates"
down_revision = "20260130_01_visit_plan_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""

    op.execute("UPDATE families SET name = 'Huismus' WHERE name = 'Zangvogel'")

    op.execute("UPDATE species SET abbreviation = 'BV' WHERE abbreviation = 'BMV'")
    op.execute("UPDATE species SET abbreviation = 'GGO' WHERE abbreviation = 'GeG'")
    op.execute("UPDATE species SET abbreviation = 'KO' WHERE abbreviation = 'KN'")


def downgrade() -> None:
    """Revert the upgrade migrations."""

    op.execute("UPDATE families SET name = 'Zangvogel' WHERE name = 'Huismus'")

    op.execute("UPDATE species SET abbreviation = 'BMV' WHERE abbreviation = 'BV'")
    op.execute("UPDATE species SET abbreviation = 'GeG' WHERE abbreviation = 'GGO'")
    op.execute("UPDATE species SET abbreviation = 'KN' WHERE abbreviation = 'KO'")

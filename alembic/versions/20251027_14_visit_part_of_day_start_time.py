"""Add part_of_day and start_time to visits

Revision ID: 20251027_14_visit_part_of_day_start_time
Revises: 20251024_13_visit_drop_status_add_planned_week
Create Date: 2025-10-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251027_14_visit_part_of_day_start_time"
down_revision = "20251024_13_visit_drop_status_week"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visits", sa.Column("part_of_day", sa.String(length=16), nullable=True)
    )
    op.add_column("visits", sa.Column("start_time", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "start_time")
    op.drop_column("visits", "part_of_day")

"""Add start_time_text to visits

Revision ID: 20251029_15_visit_start_time_text
Revises: 20251027_14_visit_part_of_day_start_time
Create Date: 2025-10-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251029_15_visit_start_time_text"
down_revision = "20251027_14_visit_part_of_day_start_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visits", sa.Column("start_time_text", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("visits", "start_time_text")


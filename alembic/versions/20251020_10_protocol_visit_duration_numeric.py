"""Change visit_duration_hours to Numeric(4,1)

Revision ID: 20251020_10_visit_duration_num
Revises: 20251020_09_protocol_periods_drop
Create Date: 2025-10-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251020_10_visit_duration_num"
down_revision = "20251020_09_protocol_periods_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "protocols",
        "visit_duration_hours",
        type_=sa.Numeric(4, 1),
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Convert back to integer, rounding as needed (DB may enforce cast)
    op.alter_column(
        "protocols",
        "visit_duration_hours",
        type_=sa.Integer(),
        existing_type=sa.Numeric(4, 1),
        existing_nullable=True,
    )

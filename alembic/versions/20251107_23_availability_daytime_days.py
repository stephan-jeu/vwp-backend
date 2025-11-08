"""availability: add daytime_days column

Revision ID: 20251107_23_avail_daytime_days
Revises: 20251106_22_avail_week_upd
Create Date: 2025-11-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251107_23_avail_daytime_days"
down_revision = "20251106_22_avail_week_upd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new column with server default 0 for existing rows
    op.add_column(
        "availability_weeks",
        sa.Column("daytime_days", sa.Integer(), nullable=False, server_default="0"),
    )
    # Optional: drop server default after backfill to rely on application-level defaults
    try:
        op.alter_column(
            "availability_weeks",
            "daytime_days",
            server_default=None,
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    except Exception:
        # Some backends may not support altering defaults in this context
        pass


def downgrade() -> None:
    op.drop_column("availability_weeks", "daytime_days")

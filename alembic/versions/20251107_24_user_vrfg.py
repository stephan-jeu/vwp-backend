"""user: add vrfg boolean

Revision ID: 20251107_24_user_vrfg
Revises: 20251107_23_avail_daytime_days
Create Date: 2025-11-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251107_24_user_vrfg"
down_revision = "20251107_23_avail_daytime_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("vrfg", sa.Boolean(), nullable=False, server_default="false"),
    )
    # drop server_default to keep application-level defaulting
    try:
        op.alter_column(
            "users",
            "vrfg",
            server_default=None,
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_column("users", "vrfg")

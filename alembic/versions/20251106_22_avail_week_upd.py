"""availability week model update: drop year, rename daytime->morning

Revision ID: 20251106_22_avail_week_upd
Revises: 20251104_21_user_enum_and_drop_huismus
Create Date: 2025-11-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251106_22_avail_week_upd"
down_revision = "20251104_21_user_enum_and_drop_huismus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old unique constraint including year
    op.drop_constraint(
        "uq_user_year_week", "availability_weeks", type_="unique"
    )
    # Rename daytime_days -> morning_days
    op.alter_column(
        "availability_weeks",
        "daytime_days",
        new_column_name="morning_days",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    # Drop year column
    op.drop_column("availability_weeks", "year")
    # Create new unique constraint without year
    op.create_unique_constraint(
        "uq_user_week", "availability_weeks", ["user_id", "week"]
    )


def downgrade() -> None:
    # Drop new unique constraint
    op.drop_constraint("uq_user_week", "availability_weeks", type_="unique")
    # Re-add year column (nullable=False with temporary default for existing rows)
    op.add_column(
        "availability_weeks",
        sa.Column("year", sa.Integer(), nullable=False, server_default="0"),
    )
    # Rename morning_days back to daytime_days
    op.alter_column(
        "availability_weeks",
        "morning_days",
        new_column_name="daytime_days",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    # Restore original unique constraint
    op.create_unique_constraint(
        "uq_user_year_week", "availability_weeks", ["user_id", "year", "week"]
    )
    # Optional: remove server_default if set above (databases differ)
    try:
        op.alter_column(
            "availability_weeks", "year", server_default=None, existing_type=sa.Integer()
        )
    except Exception:
        # Safe to ignore if backend doesn't support altering default in this context
        pass

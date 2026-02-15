"""add availability_patterns table

Revision ID: 96ed5f6ba63c
Revises: 7e85b56c5afc
Create Date: 2026-02-15 13:00:50.609507

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '96ed5f6ba63c'
down_revision = '7e85b56c5afc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""
    op.create_table(
        "availability_patterns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("max_visits_per_week", sa.Integer(), nullable=True),
        sa.Column(
            "schedule",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_availability_patterns_user_id"),
        "availability_patterns",
        ["user_id"],
        unique=False,
    )
    op.create_foreign_key(
        None, "availability_patterns", "users", ["user_id"], ["id"]
    )


def downgrade() -> None:
    """Revert the upgrade migrations."""
    op.drop_table("availability_patterns")

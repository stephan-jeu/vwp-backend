"""Add activity_log_actors junction table for multi-actor support.

Revision ID: 20260217_01_activity_log_actors
Revises: 5da6360634fb
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op

revision = "20260217_01_activity_log_actors"
down_revision = "5da6360634fb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_log_actors",
        sa.Column("activity_log_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["activity_log_id"], ["activity_logs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("activity_log_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("activity_log_actors")

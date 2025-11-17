"""Create activity_logs table and drop legacy visit_logs

Revision ID: 20251116_02_activity_log
Revises: 20251115_01_soft_delete
Create Date: 2025-11-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20251116_02_activity_log"
down_revision: Union[str, None] = "20251115_01_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the ActivityLog schema changes.

    This migration introduces the generic ``activity_logs`` table used for
    unified audit logging and removes the legacy ``visit_logs`` table.
    """

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("batch_id", sa.String(length=64), nullable=True),
    )

    op.create_index(
        op.f("ix_activity_logs_actor_id"),
        "activity_logs",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_logs_action"),
        "activity_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_logs_target_type"),
        "activity_logs",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_logs_target_id"),
        "activity_logs",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_logs_batch_id"),
        "activity_logs",
        ["batch_id"],
        unique=False,
    )

    # Drop legacy visit_logs table (replaced by activity_logs)
    op.drop_index(op.f("ix_visit_logs_visit_id"), table_name="visit_logs")
    op.drop_table("visit_logs")


def downgrade() -> None:
    """Revert ActivityLog schema changes.

    Restores the legacy ``visit_logs`` table and removes ``activity_logs``.
    """

    # Recreate legacy visit_logs table
    op.create_table(
        "visit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("visit_id", sa.Integer(), sa.ForeignKey("visits.id"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "researcher_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column("day_period", sa.String(length=16), nullable=True),
        sa.Column(
            "deviated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deviation_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_visit_logs_visit_id"),
        "visit_logs",
        ["visit_id"],
        unique=False,
    )

    # Drop the new activity_logs table
    op.drop_index(op.f("ix_activity_logs_batch_id"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_target_id"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_target_type"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_action"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_actor_id"), table_name="activity_logs")
    op.drop_table("activity_logs")

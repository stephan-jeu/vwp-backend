"""Add schedule_group_id to visits and create visit_logs table

Revision ID: 20251024_12_visit_log_sched
Revises: 20251023_11_visit_group_id
Create Date: 2025-10-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251024_12_visit_log_sched"
down_revision = "20251023_11_visit_group_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add schedule_group_id to visits (nullable, indexed)
    op.add_column(
        "visits",
        sa.Column("schedule_group_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_visits_schedule_group_id"),
        "visits",
        ["schedule_group_id"],
        unique=False,
    )

    # Create visit_logs table
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
            "researcher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column("day_period", sa.String(length=16), nullable=True),
        sa.Column(
            "deviated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deviation_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_visit_logs_visit_id"), "visit_logs", ["visit_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_visit_logs_visit_id"), table_name="visit_logs")
    op.drop_table("visit_logs")

    op.drop_index(op.f("ix_visits_schedule_group_id"), table_name="visits")
    op.drop_column("visits", "schedule_group_id")






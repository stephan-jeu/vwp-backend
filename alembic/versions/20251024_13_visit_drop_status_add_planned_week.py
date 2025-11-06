"""Drop visits.status and add planned_week

Revision ID: 20251024_13_visit_drop_status_week
Revises: 20251024_12_visit_log_sched
Create Date: 2025-10-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251024_13_visit_drop_status_week"
down_revision = "20251024_12_visit_log_sched"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop status column and its enum type if exists
    with op.batch_alter_table("visits") as batch_op:
        # Some databases require conditional drops; assume column exists per model change
        batch_op.drop_column("status")
        batch_op.add_column(sa.Column("planned_week", sa.Integer(), nullable=True))

    # Explicitly drop enum type if it exists (PostgreSQL)
    op.execute("DROP TYPE IF EXISTS visit_status_type")


def downgrade() -> None:
    # Recreate enum type and column
    op.execute(
        "CREATE TYPE visit_status_type AS ENUM ('In te plannen', 'Ingepland', 'Uitgevoerd')"
    )
    with op.batch_alter_table("visits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.Enum(name="visit_status_type"),
                nullable=False,
                server_default="In te plannen",
            )
        )
        batch_op.drop_column("planned_week")







"""Add customer column to projects table.

Revision ID: 20260219_01
Revises: 20260217_01_activity_log_actors
Create Date: 2026-02-19
"""

import sqlalchemy as sa
from alembic import op

revision = "20260219_01"
down_revision = "20260217_01_activity_log_actors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("customer", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "customer")

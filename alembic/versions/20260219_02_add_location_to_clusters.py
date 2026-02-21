"""Add location column to clusters table.

Revision ID: 20260219_02
Revises: 20260219_01
Create Date: 2026-02-19
"""

import sqlalchemy as sa
from alembic import op

revision = "20260219_02"
down_revision = "20260219_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clusters",
        sa.Column("location", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clusters", "location")

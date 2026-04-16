"""Add lat/lon coordinates to clusters and users

Revision ID: 20260414_01
Revises: 20260408_01
Create Date: 2026-04-14 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260414_01"
down_revision = "20260408_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clusters", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("clusters", sa.Column("lon", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("lon", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "lon")
    op.drop_column("users", "lat")
    op.drop_column("clusters", "lon")
    op.drop_column("clusters", "lat")

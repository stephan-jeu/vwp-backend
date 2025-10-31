"""Widen alembic_version.version_num to 128

Revision ID: 20251020_08_alembic_verlen
Revises: 20251020_07_revert
Create Date: 2025-10-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251020_08_alembic_verlen"
down_revision = "20251020_07_revert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=128),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=32),
        existing_type=sa.String(length=128),
        existing_nullable=False,
    )





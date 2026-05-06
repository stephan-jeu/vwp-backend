"""Make visit_audits.created_by_id nullable

Allows hard-deleting a user without losing audit trail records that reference
them as the creator of a visit audit.

Revision ID: 3d27de452404
Revises: f3a9b2c7d841
Create Date: 2026-05-06 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "3d27de452404"
down_revision = "20260414_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "visit_audits",
        "created_by_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Set any NULL values to a placeholder before restoring NOT NULL constraint
    op.execute(
        "UPDATE visit_audits SET created_by_id = updated_by_id WHERE created_by_id IS NULL"
    )
    op.alter_column(
        "visit_audits",
        "created_by_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

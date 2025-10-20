"""Add requires_july_visit to protocols

Revision ID: 20251019_05_protocol_july_visit
Revises: 20251018_04_species_nullable_and_cluster_number
Create Date: 2025-10-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251019_05_protocol_july_visit"
down_revision = "20251018_04_species_cluster_upd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column("requires_july_visit", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("protocols", "requires_july_visit")

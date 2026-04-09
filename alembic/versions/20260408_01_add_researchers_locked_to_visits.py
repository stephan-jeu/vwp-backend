"""Add researchers_locked to visits.

Revision ID: 20260408_01
Revises: 20260325_01
Create Date: 2026-04-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260408_01"
down_revision = "20260325_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""
    op.add_column(
        "visits",
        sa.Column(
            "researchers_locked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    """Revert the upgrade migrations."""
    op.drop_column("visits", "researchers_locked")

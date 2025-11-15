"""
20251114_27_user_address

Add optional address column to users.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251114_27_user_address"
down_revision = "20251113_26_user_smp_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("address", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "address")

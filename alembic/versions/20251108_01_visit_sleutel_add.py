from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251108_01_visit_sleutel_add"
down_revision = "20251107_24_user_vrfg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visits",
        sa.Column("sleutel", sa.Boolean(), server_default="false", nullable=False),
    )
    try:
        op.alter_column(
            "visits",
            "sleutel",
            server_default=None,
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_column("visits", "sleutel")

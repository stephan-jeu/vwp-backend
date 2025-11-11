from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251111_25_rename_hup_hub"
down_revision = "20251108_01_visit_sleutel_add"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "hup",
        new_column_name="hub",
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.alter_column(
        "visits",
        "hup",
        new_column_name="hub",
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "hub",
        new_column_name="hup",
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.alter_column(
        "visits",
        "hub",
        new_column_name="hup",
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )

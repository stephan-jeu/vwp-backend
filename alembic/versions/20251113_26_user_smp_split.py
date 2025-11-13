"""Split SMP flag and drop vlinder; add species flags

Revision ID: 20251113_26_user_smp_split
Revises: 20251111_25_rename_hup_hub
Create Date: 2025-11-13

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251113_26_user_smp_split"
down_revision = "20251111_25_rename_hup_hub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade users table:
    - Add smp_huismus, smp_vleermuis, smp_gierzwaluw (NOT NULL DEFAULT false)
    - Add grote_vos, iepenpage, teunisbloempijlstaart (NOT NULL DEFAULT false)
    - Drop legacy smp and vlinder columns
    """
    with op.batch_alter_table("users") as batch_op:
        # Add new SMP specialization flags
        batch_op.add_column(
            sa.Column("smp_huismus", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("smp_vleermuis", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("smp_gierzwaluw", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )

        # Add species flags if not already present in older DBs
        # These are idempotent in code terms; Alembic itself cannot do IF NOT EXISTS portable,
        # so we attempt to add and let it apply in sequence migrations.
        batch_op.add_column(
            sa.Column("grote_vos", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("iepenpage", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("teunisbloempijlstaart", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )

        # Drop legacy columns
        try:
            batch_op.drop_column("smp")
        except Exception:
            # Column might already be absent in some environments
            pass
        try:
            batch_op.drop_column("vlinder")
        except Exception:
            pass


def downgrade() -> None:
    """Downgrade users table changes.
    - Recreate legacy smp and vlinder columns (NOT NULL DEFAULT false)
    - Drop newly added specialization and species flags
    """
    with op.batch_alter_table("users") as batch_op:
        # Re-add legacy columns
        batch_op.add_column(
            sa.Column("smp", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("vlinder", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )

        # Drop new columns (reverse order)
        batch_op.drop_column("teunisbloempijlstaart")
        batch_op.drop_column("iepenpage")
        batch_op.drop_column("grote_vos")
        batch_op.drop_column("smp_gierzwaluw")
        batch_op.drop_column("smp_vleermuis")
        batch_op.drop_column("smp_huismus")

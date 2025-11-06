"""User fields update (rename and new booleans)

Revision ID: 20251104_20_user_fields_update
Revises: 20251104_19_visit_drop_start_time
Create Date: 2025-11-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251104_20_user_fields_update"
down_revision = "20251104_19_visit_drop_start_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema for users.

    - Rename columns:
      - rugstreeppad -> pad
      - langoren -> langoor
      - roofvogels -> roofvogel
    - Add boolean columns (NOT NULL DEFAULT false):
      - vleermuis, zwaluw, vlinder, zangvogel, biggenkruid, schijfhoren
    """
    with op.batch_alter_table("users") as batch_op:
        # Renames
        batch_op.alter_column("rugstreeppad", new_column_name="pad")
        batch_op.alter_column("langoren", new_column_name="langoor")
        batch_op.alter_column("roofvogels", new_column_name="roofvogel")

        # New boolean columns with NOT NULL DEFAULT false
        batch_op.add_column(
            sa.Column("vleermuis", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("zwaluw", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("vlinder", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("zangvogel", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("biggenkruid", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.add_column(
            sa.Column("schijfhoren", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )



def downgrade() -> None:
    """Downgrade database schema for users.

    - Drop added boolean columns
    - Rename columns back to original names
    """
    with op.batch_alter_table("users") as batch_op:
        # Drops (reverse order)
        batch_op.drop_column("schijfhoren")
        batch_op.drop_column("biggenkruid")
        batch_op.drop_column("zangvogel")
        batch_op.drop_column("vlinder")
        batch_op.drop_column("zwaluw")
        batch_op.drop_column("vleermuis")

        # Renames back
        batch_op.alter_column("pad", new_column_name="rugstreeppad")
        batch_op.alter_column("langoor", new_column_name="langoren")
        batch_op.alter_column("roofvogel", new_column_name="roofvogels")

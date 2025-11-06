"""Update experience_bat enum (add Medior, drop GZ) and drop huismus column

Revision ID: 20251104_21_user_enum_and_drop_huismus
Revises: 20251104_20_user_fields_update
Create Date: 2025-11-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251104_21_user_enum_and_drop_huismus"
down_revision = "20251104_20_user_fields_update"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade:
    - Add 'Medior' and drop 'GZ' from experience_bat_type enum
    - Drop users.huismus column
    """
    # 1) Create a new enum type with desired values
    op.execute("CREATE TYPE experience_bat_type_new AS ENUM ('Nieuw','Junior','Medior','Senior')")

    # 2) Alter column using CASE to remap 'GZ' to 'Senior' and keep others
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN experience_bat TYPE experience_bat_type_new
        USING (
            CASE experience_bat
                WHEN 'GZ' THEN 'Senior'
                ELSE experience_bat::text
            END::experience_bat_type_new
        )
        """
    )

    # 3) Drop old enum type and rename new one to original name
    op.execute("DROP TYPE experience_bat_type")
    op.execute("ALTER TYPE experience_bat_type_new RENAME TO experience_bat_type")

    # 4) Drop unused column
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("huismus")


def downgrade() -> None:
    """Downgrade:
    - Restore enum with 'GZ' and without 'Medior' (best-effort map Medior->Junior)
    - Re-add users.huismus boolean NOT NULL DEFAULT false
    """
    # Recreate old enum
    op.execute("CREATE TYPE experience_bat_type_old AS ENUM ('Nieuw','Junior','Senior','GZ')")

    # Convert back, mapping 'Medior' to 'Junior'
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN experience_bat TYPE experience_bat_type_old
        USING (
            CASE experience_bat::text
                WHEN 'Medior' THEN 'Junior'
                ELSE experience_bat::text
            END::experience_bat_type_old
        )
        """
    )

    # Drop current and rename old back
    op.execute("DROP TYPE experience_bat_type")
    op.execute("ALTER TYPE experience_bat_type_old RENAME TO experience_bat_type")

    # Re-add column
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("huismus", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )

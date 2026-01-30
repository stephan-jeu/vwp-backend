"""remove_nieuw_from_experience_bat

Revision ID: 20260127_01_experience_bat
Revises: d1f1b83878b3
Create Date: 2026-01-27 13:55:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260127_01_experience_bat"
down_revision = "d1f1b83878b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""
    op.execute("UPDATE users SET experience_bat = NULL WHERE experience_bat = 'Nieuw'")
    op.execute("ALTER TYPE experience_bat_type RENAME TO experience_bat_type_old")
    sa.Enum("Junior", "Medior", "Senior", name="experience_bat_type").create(
        op.get_bind()
    )
    op.execute(
        "ALTER TABLE users ALTER COLUMN experience_bat "
        "TYPE experience_bat_type USING experience_bat::text::experience_bat_type"
    )
    op.execute("DROP TYPE experience_bat_type_old")


def downgrade() -> None:
    """Revert the upgrade migrations."""
    op.execute("ALTER TYPE experience_bat_type RENAME TO experience_bat_type_new")
    sa.Enum("Nieuw", "Junior", "Medior", "Senior", name="experience_bat_type").create(
        op.get_bind()
    )
    op.execute(
        "ALTER TABLE users ALTER COLUMN experience_bat "
        "TYPE experience_bat_type USING experience_bat::text::experience_bat_type"
    )
    op.execute("DROP TYPE experience_bat_type_new")

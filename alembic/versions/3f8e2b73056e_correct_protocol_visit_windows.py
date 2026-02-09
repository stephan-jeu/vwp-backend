"""correct_protocol_visit_windows

Revision ID: 3f8e2b73056e
Revises: 2c4596e9fd0b
Create Date: 2026-02-09 16:04:02.878165

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f8e2b73056e'
down_revision = '2c4596e9fd0b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""
    # Update for species group 1: RD, GD, KD, GGO, GrG, WV -> 2000-04-15
    op.execute("""
        UPDATE protocol_visit_windows
        SET window_from = '2000-04-15'
        FROM protocols p
        JOIN functions f ON p.function_id = f.id
        JOIN species s ON p.species_id = s.id
        WHERE protocol_visit_windows.protocol_id = p.id
          AND protocol_visit_windows.visit_index = 1
          AND f.name = 'Zomerverblijfplaats'
          AND s.abbreviation IN ('RD', 'GD', 'KD', 'GGO', 'GrG', 'WV')
    """)

    # Update for species group 2: BaV, BrV, FS, IV, VV -> 2000-05-15
    op.execute("""
        UPDATE protocol_visit_windows
        SET window_from = '2000-05-15'
        FROM protocols p
        JOIN functions f ON p.function_id = f.id
        JOIN species s ON p.species_id = s.id
        WHERE protocol_visit_windows.protocol_id = p.id
          AND protocol_visit_windows.visit_index = 1
          AND f.name = 'Zomerverblijfplaats'
          AND s.abbreviation IN ('BaV', 'BrV', 'FS', 'IV', 'VV')
    """)


def downgrade() -> None:
    """Revert the upgrade migrations."""
    pass

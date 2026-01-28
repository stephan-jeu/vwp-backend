"""add provisional_week and locked to visits

Revision ID: d1f1b83878b3
Revises: 8de78c8d9ed2
Create Date: 2026-01-25 12:38:59.678360

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f1b83878b3'
down_revision = '8de78c8d9ed2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""
    op.add_column('visits', sa.Column('provisional_week', sa.Integer(), nullable=True))
    op.add_column('visits', sa.Column('provisional_locked', sa.Boolean(), server_default='false', nullable=False))
    op.create_index(op.f('ix_visits_provisional_week'), 'visits', ['provisional_week'], unique=False)


def downgrade() -> None:
    """Revert the upgrade migrations."""
    op.drop_index(op.f('ix_visits_provisional_week'), table_name='visits')
    op.drop_column('visits', 'provisional_locked')
    op.drop_column('visits', 'provisional_week')

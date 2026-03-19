"""Normalize min_period_between_visits_unit to lowercase English values.

Revision ID: 20260319_01
Revises: 20260219_03
Create Date: 2026-03-19
"""

from alembic import op

revision = "20260319_01"
down_revision = "f3a9b2c7d841"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE protocols
        SET min_period_between_visits_unit = 'days'
        WHERE LOWER(min_period_between_visits_unit) IN ('dagen', 'day')
        """
    )
    op.execute(
        """
        UPDATE protocols
        SET min_period_between_visits_unit = 'weeks'
        WHERE LOWER(min_period_between_visits_unit) IN ('week', 'weken')
        """
    )


def downgrade() -> None:
    pass

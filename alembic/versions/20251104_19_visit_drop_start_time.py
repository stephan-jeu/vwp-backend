"""drop visits.start_time

Revision ID: 20251104_19_visit_drop_start_time
Revises: 20251104_18_visit_expertise_str
Create Date: 2025-11-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251104_19_visit_drop_start_time"
down_revision = "20251104_18_visit_expertise_str"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema by dropping visits.start_time."""
    with op.batch_alter_table("visits") as batch_op:
        batch_op.drop_column("start_time")


def downgrade() -> None:
    """Downgrade database schema by re-adding visits.start_time as Integer NULL."""
    with op.batch_alter_table("visits") as batch_op:
        batch_op.add_column(sa.Column("start_time", sa.Integer(), nullable=True))

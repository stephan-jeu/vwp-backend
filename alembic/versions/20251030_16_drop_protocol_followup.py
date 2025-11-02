"""Drop special_follow_up_action from protocols

Revision ID: 20251030_16_drop_protocol_followup
Revises: 20251029_15_visit_start_time_text
Create Date: 2025-10-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251030_16_drop_protocol_followup"
down_revision = "20251029_15_visit_start_time_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("protocols") as batch_op:
        batch_op.drop_column("special_follow_up_action")


def downgrade() -> None:
    with op.batch_alter_table("protocols") as batch_op:
        batch_op.add_column(
            sa.Column("special_follow_up_action", sa.String(length=255), nullable=True)
        )


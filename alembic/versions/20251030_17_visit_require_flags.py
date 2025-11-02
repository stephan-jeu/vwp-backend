"""Add visit requirement flags copied from protocol

Revision ID: 20251030_17_visit_require_flags
Revises: 20251030_16_drop_protocol_followup
Create Date: 2025-10-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251030_17_visit_require_flags"
down_revision = "20251030_16_drop_protocol_followup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("visits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "requires_morning_visit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "requires_evening_visit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "requires_june_visit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "requires_maternity_period_visit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("visits") as batch_op:
        batch_op.drop_column("requires_morning_visit")
        batch_op.drop_column("requires_evening_visit")
        batch_op.drop_column("requires_june_visit")
        batch_op.drop_column("requires_maternity_period_visit")


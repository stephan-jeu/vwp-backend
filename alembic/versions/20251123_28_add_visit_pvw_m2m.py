"""add visit_protocol_visit_windows table

Revision ID: 20251123_28_add_visit_pvw_m2m
Revises: 20251116_03_merge_quote_activity
Create Date: 2025-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20251123_28_add_visit_pvw_m2m"
down_revision = "20251116_03_merge_quote_activity"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "visit_protocol_visit_windows",
        sa.Column("visit_id", sa.Integer(), nullable=False),
        sa.Column("protocol_visit_window_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["protocol_visit_window_id"], ["protocol_visit_windows.id"], ),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"], ),
        sa.PrimaryKeyConstraint("visit_id", "protocol_visit_window_id")
    )

def downgrade() -> None:
    op.drop_table("visit_protocol_visit_windows")

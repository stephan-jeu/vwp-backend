"""Create protocol_visit_windows table

Revision ID: 20251020_06_proto_visit_win
Revises: 20251019_05_protocol_july_visit
Create Date: 2025-10-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251020_06_proto_visit_win"
down_revision = "20251019_05_protocol_july_visit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "protocol_visit_windows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "protocol_id", sa.Integer(), sa.ForeignKey("protocols.id"), nullable=False
        ),
        sa.Column("visit_index", sa.Integer(), nullable=False),
        sa.Column("window_from", sa.Date(), nullable=False),
        sa.Column("window_to", sa.Date(), nullable=False),
        sa.Column(
            "required", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_protocol_visit_windows_protocol_id"),
        "protocol_visit_windows",
        ["protocol_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_protocol_visit_idx",
        "protocol_visit_windows",
        ["protocol_id", "visit_index"],
    )
    op.create_check_constraint(
        "ck_window_range_valid",
        "protocol_visit_windows",
        "window_from <= window_to",
    )


def downgrade() -> None:
    op.drop_constraint("ck_window_range_valid", "protocol_visit_windows", type_="check")
    op.drop_constraint(
        "uq_protocol_visit_idx", "protocol_visit_windows", type_="unique"
    )
    op.drop_index(
        op.f("ix_protocol_visit_windows_protocol_id"),
        table_name="protocol_visit_windows",
    )
    op.drop_table("protocol_visit_windows")

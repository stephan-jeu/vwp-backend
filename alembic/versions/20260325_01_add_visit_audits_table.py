"""Add visit_audits table.

Revision ID: 20260325_01
Revises: 20260319_01
Create Date: 2026-03-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260325_01"
down_revision = "20260319_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visit_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("visit_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("species_functions", sa.JSON(), nullable=True),
        sa.Column("remarks", sa.String(length=2048), nullable=True),
        sa.Column("remarks_outside_pg", sa.String(length=2048), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visit_id", name="uq_visit_audits_visit_id"),
    )
    op.create_index(
        op.f("ix_visit_audits_visit_id"), "visit_audits", ["visit_id"]
    )
    op.create_index(
        op.f("ix_visit_audits_created_by_id"), "visit_audits", ["created_by_id"]
    )
    op.create_index(
        op.f("ix_visit_audits_updated_by_id"), "visit_audits", ["updated_by_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_visit_audits_updated_by_id"), table_name="visit_audits")
    op.drop_index(op.f("ix_visit_audits_created_by_id"), table_name="visit_audits")
    op.drop_index(op.f("ix_visit_audits_visit_id"), table_name="visit_audits")
    op.drop_table("visit_audits")

"""Add group_id to visits for manual grouping

Revision ID: 20251023_11_visit_group_id
Revises: 20251020_10_visit_duration_num
Create Date: 2025-10-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

import uuid


revision = "20251023_11_visit_group_id"
down_revision = "20251020_10_visit_duration_num"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add nullable column first to allow backfill
    op.add_column("visits", sa.Column("group_id", sa.String(length=64), nullable=True))

    # 2) Backfill existing rows with UUID4 strings
    conn = op.get_bind()
    visits = conn.exec_driver_sql("SELECT id FROM visits WHERE group_id IS NULL")
    ids = [row[0] for row in visits]
    for visit_id in ids:
        conn.exec_driver_sql(
            "UPDATE visits SET group_id = :gid WHERE id = :vid",
            {"gid": str(uuid.uuid4()), "vid": visit_id},
        )

    # 3) Create index for faster grouping queries
    op.create_index(op.f("ix_visits_group_id"), "visits", ["group_id"], unique=False)

    # Note: Keeping column nullable to allow manual grouping flexibility.
    # If you want to enforce presence, uncomment the NOT NULL change below after backfill.
    # op.alter_column("visits", "group_id", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_visits_group_id"), table_name="visits")
    op.drop_column("visits", "group_id")

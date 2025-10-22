"""Backfill windows from protocol period_* and drop columns

Revision ID: 20251020_09_protocol_periods_drop
Revises: 20251020_08_alembic_verlen
Create Date: 2025-10-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251020_09_protocol_periods_drop"
down_revision = "20251020_08_alembic_verlen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill windows from Protocol.period_* for protocols that don't yet have windows.
    # Case A: non-wrapping periods (from <= to) -> single window.
    op.execute(
        sa.text(
            """
            INSERT INTO protocol_visit_windows (
                protocol_id, visit_index, window_from, window_to, required, label, created_at, updated_at
            )
            SELECT p.id, 1, p.period_from, p.period_to, true, NULL, now(), now()
            FROM protocols p
            WHERE p.period_from IS NOT NULL AND p.period_to IS NOT NULL
              AND p.period_from <= p.period_to
              AND NOT EXISTS (
                  SELECT 1 FROM protocol_visit_windows w WHERE w.protocol_id = p.id
              )
            """
        )
    )

    # Case B: wrapping periods (from > to) -> split into two windows [from..Dec31] and [Jan1..to].
    # Insert first half as visit_index 1
    op.execute(
        sa.text(
            """
            INSERT INTO protocol_visit_windows (
                protocol_id, visit_index, window_from, window_to, required, label, created_at, updated_at
            )
            SELECT p.id, 1, p.period_from, DATE '2000-12-31', true, NULL, now(), now()
            FROM protocols p
            WHERE p.period_from IS NOT NULL AND p.period_to IS NOT NULL
              AND p.period_from > p.period_to
              AND NOT EXISTS (
                  SELECT 1 FROM protocol_visit_windows w WHERE w.protocol_id = p.id
              )
            """
        )
    )
    # Insert second half as visit_index 2
    op.execute(
        sa.text(
            """
            INSERT INTO protocol_visit_windows (
                protocol_id, visit_index, window_from, window_to, required, label, created_at, updated_at
            )
            SELECT p.id, 2, DATE '2000-01-01', p.period_to, true, NULL, now(), now()
            FROM protocols p
            WHERE p.period_from IS NOT NULL AND p.period_to IS NOT NULL
              AND p.period_from > p.period_to
              AND NOT EXISTS (
                  SELECT 1 FROM protocol_visit_windows w WHERE w.protocol_id = p.id
              )
            """
        )
    )

    # Drop columns
    with op.batch_alter_table("protocols") as batch_op:
        batch_op.drop_column("period_from")
        batch_op.drop_column("period_to")


def downgrade() -> None:
    # Recreate columns
    with op.batch_alter_table("protocols") as batch_op:
        batch_op.add_column(sa.Column("period_from", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("period_to", sa.Date(), nullable=True))

    # Best-effort restore from first window if available
    op.execute(
        sa.text(
            """
            UPDATE protocols p
            SET period_from = w.window_from,
                period_to = w.window_to
            FROM (
                SELECT DISTINCT ON (protocol_id) protocol_id, window_from, window_to
                FROM protocol_visit_windows
                ORDER BY protocol_id, visit_index
            ) w
            WHERE w.protocol_id = p.id
            """
        )
    )

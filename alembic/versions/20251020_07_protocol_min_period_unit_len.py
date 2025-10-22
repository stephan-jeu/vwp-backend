"""(reverted) Widen min_period_between_visits_unit to 64"""

from __future__ import annotations


revision = "20251020_07_revert"
down_revision = "20251020_06_proto_visit_win"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op; revert change
    pass


def downgrade() -> None:
    pass

"""Merge branches for project quote flag and activity log

Revision ID: 20251116_03_merge_quote_activity
Revises: 20251116_01_project_quote_flag, 20251116_02_activity_log
Create Date: 2025-11-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op  # noqa: F401  (imported for consistency; no ops needed)
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "20251116_03_merge_quote_activity"
down_revision: Union[str, Sequence[str], None] = (
    "20251116_01_project_quote_flag",
    "20251116_02_activity_log",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge heads; no schema changes."""
    pass


def downgrade() -> None:
    """Downgrade merge revision.

    This is a no-op; to fully revert, downgrade to one of the parent revisions
    explicitly.
    """
    pass

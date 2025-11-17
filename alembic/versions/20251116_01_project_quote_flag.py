"""add quote flag to projects

Revision ID: 20251116_01_project_quote_flag
Revises: gdrive_proj_20251016_03
Create Date: 2025-11-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251116_01_project_quote_flag"
down_revision: Union[str, None] = "20251115_01_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "quote",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "quote")

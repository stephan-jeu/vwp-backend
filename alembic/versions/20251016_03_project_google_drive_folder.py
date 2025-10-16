"""add google_drive_folder to projects

Revision ID: gdrive_proj_20251016_03
Revises: 20251014_02_family_visit_extras
Create Date: 2025-10-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "gdrive_proj_20251016_03"
down_revision: Union[str, None] = "20251014_02_family_visit_extras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("google_drive_folder", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "google_drive_folder")

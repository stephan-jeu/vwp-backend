"""Change cluster_number column type from integer to varchar.

Revision ID: 20260219_03
Revises: 20260219_02
Create Date: 2026-02-19
"""

import sqlalchemy as sa
from alembic import op

revision = "20260219_03"
down_revision = "20260219_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing index before altering column type
    op.drop_index("ix_clusters_cluster_number", table_name="clusters")
    op.execute(
        "ALTER TABLE clusters ALTER COLUMN cluster_number TYPE VARCHAR(64) "
        "USING cluster_number::text"
    )
    op.create_index("ix_clusters_cluster_number", "clusters", ["cluster_number"])


def downgrade() -> None:
    op.drop_index("ix_clusters_cluster_number", table_name="clusters")
    op.execute(
        "ALTER TABLE clusters ALTER COLUMN cluster_number TYPE INTEGER "
        "USING cluster_number::integer"
    )
    op.create_index("ix_clusters_cluster_number", "clusters", ["cluster_number"])

"""species: name_latin nullable + abbreviation; clusters: cluster_number

Revision ID: 20251018_04_species_cluster_upd
Revises: gdrive_proj_20251016_03
Create Date: 2025-10-18

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251018_04_species_cluster_upd"
down_revision: Union[str, None] = "gdrive_proj_20251016_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # species: make name_latin nullable and add abbreviation
    with op.batch_alter_table("species") as batch_op:
        batch_op.alter_column(
            "name_latin",
            existing_type=sa.String(length=255),
            nullable=True,
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column("abbreviation", sa.String(length=64), nullable=True)
        )
        batch_op.create_index("ix_species_abbreviation", ["abbreviation"], unique=False)

    # clusters: add cluster_number (required)
    # Add as nullable with default first if table has existing rows, then backfill and set non-nullable
    op.add_column(
        "clusters",
        sa.Column("cluster_number", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_clusters_cluster_number", "clusters", ["cluster_number"], unique=False
    )

    # If needed, you can backfill here. Since we don't have runtime here, just set server default 0 then drop it
    op.execute("UPDATE clusters SET cluster_number = 0 WHERE cluster_number IS NULL")
    op.alter_column(
        "clusters", "cluster_number", nullable=False, existing_type=sa.Integer()
    )


def downgrade() -> None:
    # clusters: drop cluster_number
    op.drop_index("ix_clusters_cluster_number", table_name="clusters")
    op.drop_column("clusters", "cluster_number")

    # species: drop abbreviation and make name_latin non-nullable
    with op.batch_alter_table("species") as batch_op:
        batch_op.drop_index("ix_species_abbreviation")
        batch_op.drop_column("abbreviation")
        batch_op.alter_column(
            "name_latin",
            existing_type=sa.String(length=255),
            nullable=False,
            existing_nullable=True,
        )

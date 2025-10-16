"""family priority and visit extra fields

Revision ID: 20251014_02_family_visit_extras
Revises: 20251013_01_initial
Create Date: 2025-10-14

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20251014_02_family_visit_extras"
down_revision = "20251013_01_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # families: add priority
    op.add_column(
        "families",
        sa.Column(
            "priority", sa.Integer(), nullable=False, server_default=sa.text("5")
        ),
    )

    # visits: add new columns and enum
    visit_status = postgresql.ENUM(
        "In te plannen", "Ingepland", "Uitgevoerd", name="visit_status_type"
    )
    visit_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "visits",
        sa.Column(
            "priority", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "visits",
        sa.Column("preferred_researcher_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_visits_preferred_researcher_id_users",
        source_table="visits",
        referent_table="users",
        local_cols=["preferred_researcher_id"],
        remote_cols=["id"],
    )
    op.add_column(
        "visits",
        sa.Column(
            "status",
            postgresql.ENUM(name="visit_status_type", create_type=False),
            nullable=False,
            server_default=sa.text("'In te plannen'"),
        ),
    )
    op.add_column(
        "visits",
        sa.Column(
            "advertized", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "visits",
        sa.Column(
            "quote", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    # visits: drop added columns
    op.drop_column("visits", "quote")
    op.drop_column("visits", "advertized")
    op.drop_column("visits", "status")
    op.drop_constraint(
        "fk_visits_preferred_researcher_id_users",
        table_name="visits",
        type_="foreignkey",
    )
    op.drop_column("visits", "preferred_researcher_id")
    op.drop_column("visits", "priority")

    # drop enum if no longer used
    visit_status = postgresql.ENUM(name="visit_status_type")
    visit_status.drop(op.get_bind(), checkfirst=True)

    # families: drop priority
    op.drop_column("families", "priority")





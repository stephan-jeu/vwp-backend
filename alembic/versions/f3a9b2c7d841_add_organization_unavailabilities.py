"""Add organization_unavailabilities table

Revision ID: f3a9b2c7d841
Revises: 60574d3151a2
Create Date: 2026-03-04 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a9b2c7d841"
down_revision = "60574d3151a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_unavailabilities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("morning", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("daytime", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("nighttime", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_unavailabilities_deleted_at"),
        "organization_unavailabilities",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organization_unavailabilities_deleted_at"),
        table_name="organization_unavailabilities",
    )
    op.drop_table("organization_unavailabilities")

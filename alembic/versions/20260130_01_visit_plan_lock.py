"""visit_planning_locked

Revision ID: 20260130_01_visit_plan_lock
Revises: 20260127_01_experience_bat
Create Date: 2026-01-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260130_01_visit_plan_lock"
down_revision = "20260127_01_experience_bat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the upgrade migrations."""

    op.add_column(
        "visits",
        sa.Column(
            "planning_locked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("visits"):
        if fk.get("constrained_columns") == ["preferred_researcher_id"]:
            fk_name = fk.get("name")
            if fk_name:
                op.drop_constraint(fk_name, "visits", type_="foreignkey")
            break

    with op.batch_alter_table("visits") as batch_op:
        batch_op.drop_column("preferred_researcher_id")


def downgrade() -> None:
    """Revert the upgrade migrations."""

    with op.batch_alter_table("visits") as batch_op:
        batch_op.add_column(
            sa.Column("preferred_researcher_id", sa.Integer(), nullable=True)
        )

    op.create_foreign_key(
        None,
        "visits",
        "users",
        ["preferred_researcher_id"],
        ["id"],
    )

    op.drop_column("visits", "planning_locked")

"""Introduce soft deletes and partial unique indexes

Revision ID: 20251115_01_soft_delete
Revises: 20251019_05_protocol_july_visit
Create Date: 2025-11-15

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251115_01_soft_delete"
down_revision: Union[str, None] = "20251114_27_user_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add deleted_at columns (timezone-aware) + indexes
    for table in ("users", "projects", "clusters", "visits", "availability_weeks"):
        op.add_column(
            table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"], unique=False)

    # 2) Replace hard unique constraints with partial unique indexes on active rows
    # Postgres names default unique constraints as <table>_<col>_key
    # users.email
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("users_email_key", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX ux_users_email_active ON users(email) WHERE deleted_at IS NULL"
    )

    # projects.code
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("projects_code_key", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX ux_projects_code_active ON projects(code) WHERE deleted_at IS NULL"
    )

    # availability_weeks: replace uq_user_week with partial unique index
    with op.batch_alter_table("availability_weeks") as batch_op:
        batch_op.drop_constraint("uq_user_week", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX ux_availability_user_week_active ON availability_weeks(user_id, week) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # Drop partial unique indexes
    op.execute("DROP INDEX IF EXISTS ux_users_email_active")
    op.execute("DROP INDEX IF EXISTS ux_projects_code_active")
    op.execute("DROP INDEX IF EXISTS ux_availability_user_week_active")

    # Recreate unique constraints
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_unique_constraint(
            None, ["email"]
        )  # unnamed -> defaults to *_key
    with op.batch_alter_table("projects") as batch_op:
        batch_op.create_unique_constraint(
            None, ["code"]
        )  # unnamed -> defaults to *_key
    with op.batch_alter_table("availability_weeks") as batch_op:
        batch_op.create_unique_constraint(
            "uq_user_week", ["user_id", "week"]
        )  # restore

    # Drop deleted_at indexes and columns
    for table in ("users", "projects", "clusters", "visits", "availability_weeks"):
        op.drop_index(f"ix_{table}_deleted_at", table_name=table)
        op.drop_column(table, "deleted_at")

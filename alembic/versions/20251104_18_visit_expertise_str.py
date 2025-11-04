"""visit expertise string

Revision ID: 20251104_18_visit_expertise_str
Revises: 20251030_17_visit_require_flags
Create Date: 2025-11-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251104_18_visit_expertise_str"
down_revision = "20251030_17_visit_require_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema.

    Changes visits.expertise_level from BOOLEAN NOT NULL DEFAULT false to
    VARCHAR(64) NULL. Drops the server default before altering type to avoid
    casting issues on Postgres. When converting, maps TRUE -> 'Senior' and
    FALSE/NULL -> NULL. If you'd like a different mapping, adjust accordingly.
    """
    # Change visits.expertise_level from boolean NOT NULL default false -> VARCHAR(64) NULL
    # 1) Drop server default to avoid casting issues
    op.alter_column(
        "visits",
        "expertise_level",
        server_default=None,
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    # 2) Drop NOT NULL first so USING expression can yield NULLs safely
    op.alter_column(
        "visits",
        "expertise_level",
        existing_type=sa.Boolean(),
        nullable=True,
    )
    # 3) Change type with USING clause
    op.alter_column(
        "visits",
        "expertise_level",
        type_=sa.String(length=64),
        existing_type=sa.Boolean(),
        postgresql_using="CASE WHEN expertise_level IS TRUE THEN 'Senior' ELSE NULL END",
    )


def downgrade() -> None:
    """Downgrade database schema.

    Reverts visits.expertise_level back to BOOLEAN NOT NULL DEFAULT false.
    Maps 'Senior' (case-insensitive) to true; all other values (including NULL)
    to false.
    """
    # Best-effort reverse: map any non-null, case-insensitive 'true' to true; otherwise false
    op.alter_column(
        "visits",
        "expertise_level",
        type_=sa.Boolean(),
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=sa.text("false"),
        postgresql_using=(
            "CASE WHEN expertise_level ILIKE 'senior' THEN true ELSE false END"
        ),
    )

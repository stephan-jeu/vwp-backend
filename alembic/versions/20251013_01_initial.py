"""initial schema

Revision ID: 20251013_01_initial
Revises:
Create Date: 2025-10-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20251013_01_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Timestamp helper
    timestamp_kwargs = {
        "timezone": True,
    }

    # Enums
    contract_type = postgresql.ENUM("Intern", "Flex", "ZZP", name="contract_type")
    experience_bat_type = postgresql.ENUM(
        "Nieuw", "Junior", "Senior", "GZ", name="experience_bat_type"
    )

    contract_type.create(op.get_bind(), checkfirst=True)
    experience_bat_type.create(op.get_bind(), checkfirst=True)

    # families
    op.create_table(
        "families",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_families_name", "families", ["name"], unique=False)

    # species
    op.create_table(
        "species",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_latin", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("name_latin"),
    )
    op.create_index("ix_species_family_id", "species", ["family_id"], unique=False)
    op.create_index("ix_species_name", "species", ["name"], unique=False)
    op.create_index("ix_species_name_latin", "species", ["name_latin"], unique=False)

    # functions
    op.create_table(
        "functions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_functions_name", "functions", ["name"], unique=False)

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "admin", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("city", sa.String(length=255), nullable=True),
        # use existing enums without attempting to (re)create on table create
        sa.Column(
            "contract",
            postgresql.ENUM(name="contract_type", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "experience_bat",
            postgresql.ENUM(name="experience_bat_type", create_type=False),
            nullable=True,
        ),
        sa.Column("smp", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "rugstreeppad",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "huismus", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "langoren", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "roofvogels", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("wbc", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "fiets", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("hup", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dvp", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    # projects
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_projects_code", "projects", ["code"], unique=False)

    # clusters
    op.create_table(
        "clusters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_clusters_project_id", "clusters", ["project_id"], unique=False)

    # protocols
    op.create_table(
        "protocols",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "species_id", sa.Integer(), sa.ForeignKey("species.id"), nullable=False
        ),
        sa.Column(
            "function_id", sa.Integer(), sa.ForeignKey("functions.id"), nullable=False
        ),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("visits", sa.Integer(), nullable=True),
        sa.Column("visit_duration_hours", sa.Integer(), nullable=True),
        sa.Column("min_period_between_visits_value", sa.Integer(), nullable=True),
        sa.Column(
            "min_period_between_visits_unit", sa.String(length=32), nullable=True
        ),
        sa.Column("start_timing_reference", sa.String(length=64), nullable=True),
        sa.Column("start_time_relative_minutes", sa.Integer(), nullable=True),
        sa.Column("start_time_absolute_from", sa.Time(timezone=False), nullable=True),
        sa.Column("start_time_absolute_to", sa.Time(timezone=False), nullable=True),
        sa.Column("end_timing_reference", sa.String(length=64), nullable=True),
        sa.Column("end_time_relative_minutes", sa.Integer(), nullable=True),
        sa.Column("min_temperature_celsius", sa.Integer(), nullable=True),
        sa.Column("max_wind_force_bft", sa.Integer(), nullable=True),
        sa.Column("max_precipitation", sa.String(length=64), nullable=True),
        sa.Column("start_time_condition", sa.String(length=255), nullable=True),
        sa.Column("end_time_condition", sa.String(length=255), nullable=True),
        sa.Column("visit_conditions_text", sa.String(length=1024), nullable=True),
        sa.Column(
            "requires_morning_visit",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "requires_evening_visit",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "requires_june_visit",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "requires_maternity_period_visit",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("special_follow_up_action", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_protocols_species_id", "protocols", ["species_id"], unique=False
    )
    op.create_index(
        "ix_protocols_function_id", "protocols", ["function_id"], unique=False
    )

    # visits
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "cluster_id", sa.Integer(), sa.ForeignKey("clusters.id"), nullable=False
        ),
        sa.Column("required_researchers", sa.Integer(), nullable=True),
        sa.Column("visit_nr", sa.Integer(), nullable=True),
        sa.Column("from", sa.Date(), nullable=True),
        sa.Column("to", sa.Date(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("min_temperature_celsius", sa.Integer(), nullable=True),
        sa.Column("max_wind_force_bft", sa.Integer(), nullable=True),
        sa.Column("max_precipitation", sa.String(length=64), nullable=True),
        sa.Column(
            "expertise_level",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("wbc", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "fiets", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("hup", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dvp", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("remarks_planning", sa.String(length=1024), nullable=True),
        sa.Column("remarks_field", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_visits_cluster_id", "visits", ["cluster_id"], unique=False)

    # visit association tables
    op.create_table(
        "visit_functions",
        sa.Column(
            "visit_id", sa.Integer(), sa.ForeignKey("visits.id"), primary_key=True
        ),
        sa.Column(
            "function_id", sa.Integer(), sa.ForeignKey("functions.id"), primary_key=True
        ),
    )
    op.create_table(
        "visit_species",
        sa.Column(
            "visit_id", sa.Integer(), sa.ForeignKey("visits.id"), primary_key=True
        ),
        sa.Column(
            "species_id", sa.Integer(), sa.ForeignKey("species.id"), primary_key=True
        ),
    )
    op.create_table(
        "visit_researchers",
        sa.Column(
            "visit_id", sa.Integer(), sa.ForeignKey("visits.id"), primary_key=True
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
    )

    # availability weeks
    op.create_table(
        "availability_weeks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column(
            "daytime_days", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "nighttime_days", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "flex_days", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(**timestamp_kwargs),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "year", "week", name="uq_user_year_week"),
    )
    op.create_index(
        "ix_availability_weeks_user_id", "availability_weeks", ["user_id"], unique=False
    )


def downgrade() -> None:
    # Drop in reverse order of dependencies
    op.drop_index("ix_availability_weeks_user_id", table_name="availability_weeks")
    op.drop_table("availability_weeks")

    op.drop_table("visit_researchers")
    op.drop_table("visit_species")
    op.drop_table("visit_functions")

    op.drop_index("ix_visits_cluster_id", table_name="visits")
    op.drop_table("visits")

    op.drop_index("ix_protocols_function_id", table_name="protocols")
    op.drop_index("ix_protocols_species_id", table_name="protocols")
    op.drop_table("protocols")

    op.drop_index("ix_clusters_project_id", table_name="clusters")
    op.drop_table("clusters")

    op.drop_index("ix_projects_code", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_functions_name", table_name="functions")
    op.drop_table("functions")

    op.drop_index("ix_species_name_latin", table_name="species")
    op.drop_index("ix_species_name", table_name="species")
    op.drop_index("ix_species_family_id", table_name="species")
    op.drop_table("species")

    op.drop_index("ix_families_name", table_name="families")
    op.drop_table("families")

    # Enums
    contract_type = postgresql.ENUM(name="contract_type")
    experience_bat_type = postgresql.ENUM(name="experience_bat_type")
    experience_bat_type.drop(op.get_bind(), checkfirst=True)
    contract_type.drop(op.get_bind(), checkfirst=True)

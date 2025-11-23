from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Table, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, SoftDeleteMixin
from app.models.cluster import Cluster
from app.models.function import Function
from app.models.species import Species
from app.models.user import User
from app.models.protocol_visit_window import ProtocolVisitWindow


# Association tables for many-to-many relationships
visit_functions = Table(
    "visit_functions",
    Base.metadata,
    Column("visit_id", ForeignKey("visits.id"), primary_key=True),
    Column("function_id", ForeignKey("functions.id"), primary_key=True),
)

visit_species = Table(
    "visit_species",
    Base.metadata,
    Column("visit_id", ForeignKey("visits.id"), primary_key=True),
    Column("species_id", ForeignKey("species.id"), primary_key=True),
)

visit_researchers = Table(
    "visit_researchers",
    Base.metadata,
    Column("visit_id", ForeignKey("visits.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)

visit_protocol_visit_windows = Table(
    "visit_protocol_visit_windows",
    Base.metadata,
    Column("visit_id", ForeignKey("visits.id"), primary_key=True),
    Column(
        "protocol_visit_window_id",
        ForeignKey("protocol_visit_windows.id"),
        primary_key=True,
    ),
)


class Visit(TimestampMixin, SoftDeleteMixin, Base):
    """Central planning entity representing a field visit."""

    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey(Cluster.id), nullable=False, index=True
    )
    cluster: Mapped[Cluster] = relationship(Cluster)

    # Many-to-many relations
    functions: Mapped[list[Function]] = relationship(
        Function, secondary=visit_functions
    )
    species: Mapped[list[Species]] = relationship(Species, secondary=visit_species)
    researchers: Mapped[list[User]] = relationship(User, secondary=visit_researchers)
    protocol_visit_windows: Mapped[list[ProtocolVisitWindow]] = relationship(
        ProtocolVisitWindow, secondary="visit_protocol_visit_windows"
    )

    # Free-form grouping identifier to link related visits.
    # Populated with a random string (UUID4) on creation; can be edited to group visits.
    group_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, default=lambda: str(uuid4())
    )

    # Ephemeral grouping used for weekly planning to combine visits ad-hoc
    schedule_group_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    required_researchers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visit_nr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_date: Mapped[date | None] = mapped_column("from", nullable=True)
    to_date: Mapped[date | None] = mapped_column("to", nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_temperature_celsius: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_wind_force_bft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_precipitation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expertise_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wbc: Mapped[bool] = mapped_column(default=False, server_default="false")
    fiets: Mapped[bool] = mapped_column(default=False, server_default="false")
    hub: Mapped[bool] = mapped_column(default=False, server_default="false")
    dvp: Mapped[bool] = mapped_column(default=False, server_default="false")
    sleutel: Mapped[bool] = mapped_column(default=False, server_default="false")
    requires_morning_visit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    requires_evening_visit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    requires_june_visit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    requires_maternity_period_visit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    remarks_planning: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    remarks_field: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    priority: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Derived/planning helper fields to persist
    part_of_day: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Human-readable Dutch representation of the start time (derived but persisted)
    start_time_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_researcher_id: Mapped[int | None] = mapped_column(
        ForeignKey(User.id), nullable=True
    )
    preferred_researcher: Mapped[User | None] = relationship(User)

    # Optional ISO week number the visit is planned for
    planned_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    advertized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    quote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

from __future__ import annotations

from datetime import date

from sqlalchemy import ForeignKey, Integer, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models import Base, TimestampMixin
from backend.app.models.cluster import Cluster
from backend.app.models.function import Function
from backend.app.models.species import Species
from backend.app.models.user import User


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


class Visit(TimestampMixin, Base):
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

    required_researchers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visit_nr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_date: Mapped[date | None] = mapped_column("from", nullable=True)
    to_date: Mapped[date | None] = mapped_column("to", nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_temperature_celsius: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_wind_force_bft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_precipitation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expertise_level: Mapped[bool] = mapped_column(default=False, server_default="false")
    wbc: Mapped[bool] = mapped_column(default=False, server_default="false")
    fiets: Mapped[bool] = mapped_column(default=False, server_default="false")
    hup: Mapped[bool] = mapped_column(default=False, server_default="false")
    dvp: Mapped[bool] = mapped_column(default=False, server_default="false")
    remarks_planning: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    remarks_field: Mapped[str | None] = mapped_column(String(1024), nullable=True)

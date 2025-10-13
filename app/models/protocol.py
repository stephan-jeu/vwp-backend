from __future__ import annotations

from datetime import date, time

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models import Base, TimestampMixin
from backend.app.models.function import Function
from backend.app.models.species import Species


class Protocol(TimestampMixin, Base):
    """Field protocol definition for planning visits.

    Many fields are optional and can be used to constrain planning.
    """

    __tablename__ = "protocols"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    species_id: Mapped[int] = mapped_column(
        ForeignKey(Species.id), nullable=False, index=True
    )
    function_id: Mapped[int] = mapped_column(
        ForeignKey(Function.id), nullable=False, index=True
    )

    species: Mapped[Species] = relationship(Species)
    function: Mapped[Function] = relationship(Function)

    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    visits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visit_duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_period_between_visits_value: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    min_period_between_visits_unit: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    start_timing_reference: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    start_time_relative_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    start_time_absolute_from: Mapped[time | None] = mapped_column(
        Time(timezone=False), nullable=True
    )
    start_time_absolute_to: Mapped[time | None] = mapped_column(
        Time(timezone=False), nullable=True
    )
    end_timing_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_time_relative_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    min_temperature_celsius: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_wind_force_bft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_precipitation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_time_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_time_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visit_conditions_text: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    requires_morning_visit: Mapped[bool] = mapped_column(
        default=False, server_default="false"
    )
    requires_evening_visit: Mapped[bool] = mapped_column(
        default=False, server_default="false"
    )
    requires_june_visit: Mapped[bool] = mapped_column(
        default=False, server_default="false"
    )
    requires_maternity_period_visit: Mapped[bool] = mapped_column(
        default=False, server_default="false"
    )
    special_follow_up_action: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

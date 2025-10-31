from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel


class ProtocolBase(BaseModel):
    species_id: int
    function_id: int
    visits: int | None = None
    visit_duration_hours: int | None = None
    min_period_between_visits_value: int | None = None
    min_period_between_visits_unit: str | None = None
    start_timing_reference: str | None = None
    start_time_relative_minutes: int | None = None
    start_time_absolute_from: time | None = None
    start_time_absolute_to: time | None = None
    end_timing_reference: str | None = None
    end_time_relative_minutes: int | None = None
    min_temperature_celsius: int | None = None
    max_wind_force_bft: int | None = None
    max_precipitation: str | None = None
    start_time_condition: str | None = None
    end_time_condition: str | None = None
    visit_conditions_text: str | None = None
    requires_morning_visit: bool = False
    requires_evening_visit: bool = False
    requires_june_visit: bool = False
    requires_maternity_period_visit: bool = False
    # Optional nested windows when creating/updating a protocol
    # Note: create types defined below
    visit_windows: list["ProtocolVisitWindowCreate"] | None = None


class ProtocolCreate(ProtocolBase):
    pass


class ProtocolRead(ProtocolBase):
    id: int
    visit_windows: list["ProtocolVisitWindowRead"] = []

    model_config = {"from_attributes": True}


class ProtocolVisitWindowBase(BaseModel):
    visit_index: int
    window_from: date
    window_to: date
    required: bool = True
    label: str | None = None


class ProtocolVisitWindowCreate(ProtocolVisitWindowBase):
    pass


class ProtocolVisitWindowRead(ProtocolVisitWindowBase):
    id: int

    model_config = {"from_attributes": True}

from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from app.schemas.function import FunctionRead
from app.schemas.species import SpeciesRead
from app.schemas.user import UserNameRead


class VisitBase(BaseModel):
    """Shared Visit fields used for create and read operations.

    This excludes nested relations, which are only present on read.
    """

    cluster_id: int
    required_researchers: int | None = None
    visit_nr: int | None = None
    from_date: date | None = None
    to_date: date | None = None
    duration: int | None = None
    min_temperature_celsius: int | None = None
    max_wind_force_bft: int | None = None
    max_precipitation: str | None = None
    planned_week: int | None = None
    expertise_level: str | None = None
    wbc: bool = False
    fiets: bool = False
    hup: bool = False
    dvp: bool = False
    requires_morning_visit: bool = False
    requires_evening_visit: bool = False
    requires_june_visit: bool = False
    requires_maternity_period_visit: bool = False
    remarks_planning: str | None = None
    remarks_field: str | None = None
    priority: bool = False
    preferred_researcher_id: int | None = None
    advertized: bool = False
    quote: bool = False
    # Derived planning helpers (not persisted)
    part_of_day: str | None = None
    # Human-readable Dutch representation of the start time
    start_time_text: str | None = None


class VisitCreate(VisitBase):
    """Payload for creating a Visit.

    Many-to-many relations are provided as ID lists on create to keep writes simple.
    """

    function_ids: list[int] | None = None
    species_ids: list[int] | None = None
    researcher_ids: list[int] | None = None


class VisitRead(VisitBase):
    """Read model for Visit with nested related objects for UI display."""

    id: int
    functions: list[FunctionRead] = []
    species: list[SpeciesRead] = []
    researchers: list[UserNameRead] = []

    model_config = {"from_attributes": True}


class VisitUpdate(BaseModel):
    """Payload for updating a Visit from table edits.

    All fields are optional; only provided values will be persisted. Relation
    updates for functions/species can be done via their *_ids lists.
    """

    required_researchers: int | None = None
    visit_nr: int | None = None
    from_date: date | None = None
    to_date: date | None = None
    duration: int | None = None
    min_temperature_celsius: int | None = None
    max_wind_force_bft: int | None = None
    max_precipitation: str | None = None
    planned_week: int | None = None
    expertise_level: str | None = None
    wbc: bool | None = None
    fiets: bool | None = None
    hup: bool | None = None
    dvp: bool | None = None
    remarks_planning: str | None = None
    remarks_field: str | None = None
    priority: bool | None = None
    preferred_researcher_id: int | None = None
    advertized: bool | None = None
    quote: bool | None = None
    # Allow manual override of derived planning helpers
    part_of_day: str | None = None
    start_time_text: str | None = None
    function_ids: list[int] | None = None
    species_ids: list[int] | None = None

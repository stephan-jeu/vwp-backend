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
    expertise_level: bool = False
    wbc: bool = False
    fiets: bool = False
    hup: bool = False
    dvp: bool = False
    remarks_planning: str | None = None
    remarks_field: str | None = None
    priority: bool = False
    preferred_researcher_id: int | None = None
    status: str = "In te plannen"
    advertized: bool = False
    quote: bool = False


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

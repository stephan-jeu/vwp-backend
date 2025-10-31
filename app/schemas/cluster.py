from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from app.schemas.function import FunctionCompactRead
from app.schemas.species import SpeciesCompactRead


class ClusterCreate(BaseModel):
    """Payload to create a cluster and optionally generate visits.

    Attributes:
        project_id: Parent project identifier.
        address: Address string.
        cluster_number: Cluster sequence number within project.
        function_ids: Selected function ids used for visit generation.
        species_ids: Selected species ids used for visit generation.
    """

    project_id: int
    address: str = Field(min_length=1, max_length=255)
    cluster_number: int
    function_ids: list[int] = []
    species_ids: list[int] = []


class ClusterDuplicate(BaseModel):
    """Payload to duplicate a cluster into a new cluster row."""

    cluster_number: int
    address: str = Field(min_length=1, max_length=255)


class VisitReadCompact(BaseModel):
    """Compact visit representation for tables.

    Includes both id arrays for mutation compatibility and compact nested
    objects for UI display needs.
    """

    id: int
    cluster_id: int
    function_ids: list[int]
    species_ids: list[int]
    functions: list[FunctionCompactRead] = []
    species: list[SpeciesCompactRead] = []
    # planning helpers
    part_of_day: str | None = None
    start_time: int | None = None
    start_time_text: str | None = None
    group_id: str | None
    required_researchers: int | None
    visit_nr: int | None
    from_date: date | None
    to_date: date | None
    duration: int | None
    min_temperature_celsius: int | None
    max_wind_force_bft: int | None
    max_precipitation: str | None
    expertise_level: bool
    wbc: bool
    fiets: bool
    hup: bool
    dvp: bool
    remarks_planning: str | None
    remarks_field: str | None


class ClusterRead(BaseModel):
    id: int
    project_id: int
    address: str
    cluster_number: int


class ClusterWithVisitsRead(ClusterRead):
    visits: list[VisitReadCompact]


class ClusterVisitRow(BaseModel):
    """Flattened row combining cluster and visit information for tables.

    Attributes:
        id: Visit id.
        cluster_id: Owning cluster id.
        cluster_number: Cluster number (for grouping in UI).
        cluster_address: Cluster address string.
        function_ids: Selected function ids on the visit.
        species_ids: Selected species ids on the visit.
        required_researchers: Required researchers for the visit.
        visit_nr: Visit sequence number.
        from_date: Start date.
        to_date: End date.
        duration: Duration in minutes.
        min_temperature_celsius: Minimum temperature condition.
        max_wind_force_bft: Maximum wind force condition.
        max_precipitation: Maximum precipitation condition.
        expertise_level: Whether expertise is required.
        wbc: WBC flag.
        fiets: Bicycle required flag.
        hup: HuP flag.
        dvp: DvP flag.
        remarks_planning: Planner remarks.
        remarks_field: Field remarks.
        start_time_text: Optional human-readable start time description.
    """

    id: int
    cluster_id: int
    cluster_number: int
    cluster_address: str
    function_ids: list[int]
    species_ids: list[int]
    functions: list[FunctionCompactRead] = []
    species: list[SpeciesCompactRead] = []
    required_researchers: int | None
    visit_nr: int | None
    from_date: date | None
    to_date: date | None
    duration: int | None
    min_temperature_celsius: int | None
    max_wind_force_bft: int | None
    max_precipitation: str | None
    expertise_level: bool
    wbc: bool
    fiets: bool
    hup: bool
    dvp: bool
    remarks_planning: str | None
    remarks_field: str | None
    start_time_text: str | None = None

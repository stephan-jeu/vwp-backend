from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from app.schemas.function import FunctionCompactRead
from app.schemas.species import SpeciesCompactRead
from app.schemas.user import UserNameRead


class SpeciesFunctionCombo(BaseModel):
    """Species–function combination input for visit generation.

    Args:
        function_ids: One or more function ids.
        species_ids: One or more species ids.

    Returns:
        Validated combination object used to resolve matching protocols.
    """

    function_ids: list[int] = Field(min_length=1)
    species_ids: list[int] = Field(min_length=1)


class ClusterCreate(BaseModel):
    """Payload to create a cluster and optionally generate visits.

    Attributes:
        project_id: Parent project identifier.
        address: Address string.
        cluster_number: Cluster sequence number within project.
        combos: One or more species–function combinations to resolve to protocols.
    """

    project_id: int
    address: str = Field(min_length=1, max_length=255)
    cluster_number: int
    combos: list[SpeciesFunctionCombo] = Field(default_factory=list)
    default_required_researchers: int | None = None
    default_planned_week: int | None = None
    default_researcher_ids: list[int] | None = None
    default_planning_locked: bool = False
    default_expertise_level: str | None = None
    default_wbc: bool = False
    default_fiets: bool = False
    default_hub: bool = False
    default_dvp: bool = False
    default_sleutel: bool = False
    default_remarks_field: str | None = None


class ClusterDuplicate(BaseModel):
    """Payload to duplicate a cluster into a new cluster row."""

    cluster_number: int
    address: str = Field(min_length=1, max_length=255)


class ClusterUpdate(BaseModel):
    """Payload to update fields on a cluster.

    Attributes:
        address: New address string.
    """

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
    expertise_level: str | None
    wbc: bool
    fiets: bool
    hub: bool
    dvp: bool
    sleutel: bool
    remarks_planning: str | None
    remarks_field: str | None
    priority: bool
    planned_week: int | None = None
    planning_locked: bool = False
    researcher_ids: list[int] = []
    researchers: list[UserNameRead] = []


class ClusterRead(BaseModel):
    id: int
    project_id: int
    address: str
    cluster_number: int


class ClusterWithVisitsRead(ClusterRead):
    visits: list[VisitReadCompact]
    warnings: list[str] = []


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
        hub: HUB flag.
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
    expertise_level: str | None
    wbc: bool
    fiets: bool
    hub: bool
    dvp: bool
    sleutel: bool
    remarks_planning: str | None
    remarks_field: str | None
    start_time_text: str | None = None

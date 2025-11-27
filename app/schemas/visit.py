from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.function import FunctionRead, FunctionCompactRead
from app.schemas.species import SpeciesRead, SpeciesCompactRead
from app.schemas.user import UserNameRead
from app.services.visit_status_service import VisitStatusCode


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
    hub: bool = False
    dvp: bool = False
    sleutel: bool = False
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
    hub: bool | None = None
    dvp: bool | None = None
    sleutel: bool | None = None
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
    researcher_ids: list[int] | None = None


class VisitExecuteRequest(BaseModel):
    """Payload for marking a visit as executed without protocol deviation.

    Args:
        execution_date: Calendar date when the visit was executed.
        comment: Optional free-text comment from the executor.
    """

    execution_date: date
    comment: str | None = None


class VisitExecuteDeviationRequest(BaseModel):
    """Payload for marking a visit as executed with a protocol deviation.

    Args:
        execution_date: Calendar date when the visit was executed.
        reason: Required explanation of the deviation.
        comment: Optional additional context.
    """

    execution_date: date
    reason: str
    comment: str | None = None


class VisitNotExecutedRequest(BaseModel):
    """Payload for marking a visit as not executed.

    Args:
        date: Calendar date relevant to the non-execution decision.
        reason: Required explanation why the visit was not executed.
    """

    date: date
    reason: str


class VisitAdvertisedRequest(BaseModel):
    """Payload for toggling the advertised flag of a visit.

    Args:
        advertized: Desired advertised state. ``True`` marks the visit as
            advertised for takeover, ``False`` cancels the advertisement.
    """

    advertized: bool


class VisitAdminPlanningStatusRequest(BaseModel):
    """Payload for admin-driven planning status adjustments.

    Args:
        mode: Desired planning mode for the visit (``"open"`` or ``"planned"``).
        planned_week: Optional ISO week number when planning the visit.
        researcher_ids: Optional list of researcher ids to assign when
            planning the visit.
    """

    mode: str
    planned_week: int | None = None
    researcher_ids: list[int] | None = None
    comment: str | None = None


class VisitAuditPayload(BaseModel):
    """Audit metadata captured when approving or rejecting a visit.

    Args:
        errors: Machine-readable error codes representing protocol deviations.
        errors_comment: Optional free-text comment explaining the errors.
        errors_fixed: Whether the errors have been corrected.
        pg_hm_function: Optional text for PG: HM-functie.
        pg_vm_function: Optional text for PG: VM-functie.
        pg_gz_function: Optional text for PG: GZ-functie.
        pg_other_species: Optional text for PG: andere soort.
        remarks_outside_pg: Optional text for bijzonderheden buiten PG.
        remarks: Optional general remarks.
    """

    errors: list[str] = Field(default_factory=list)
    errors_comment: str | None = None
    errors_fixed: bool = False
    pg_hm_function: str | None = None
    pg_vm_function: str | None = None
    pg_gz_function: str | None = None
    pg_other_species: str | None = None
    remarks_outside_pg: str | None = None
    remarks: str | None = None


class VisitApprovalRequest(BaseModel):
    """Payload for approving a visit result.

    Args:
        comment: Required approval comment or justification.
        audit: Optional structured audit metadata captured during review.
    """

    comment: str
    audit: VisitAuditPayload | None = None


class VisitRejectionRequest(BaseModel):
    """Payload for rejecting a visit result.

    Args:
        reason: Required explanation for the rejection.
        audit: Optional structured audit metadata captured during review.
    """

    reason: str
    audit: VisitAuditPayload | None = None


class VisitListRow(BaseModel):
    """Flattened row for the visits overview table.

    This combines project, cluster and visit information plus a derived
    lifecycle status for efficient table rendering.

    Attributes:
        id: Visit primary key.
        project_code: Project code for grouping and filters.
        project_location: Human-readable project location.
        project_google_drive_folder: Optional Google Drive folder URL for the
            parent project.
        cluster_id: Owning cluster identifier.
        cluster_number: Cluster number within the project.
        cluster_address: Address associated with the cluster.
        status: Derived lifecycle status code.
        function_ids: Selected function ids on the visit.
        species_ids: Selected species ids on the visit.
        functions: Compact function representations.
        species: Compact species representations.
        required_researchers: Required researcher count.
        visit_nr: Visit sequence number within the cluster.
        from_date: Start date of the visit window.
        to_date: End date of the visit window.
        duration: Duration in minutes.
        execution_date: Optional date the visit was executed, when known.
        min_temperature_celsius: Minimum temperature constraint.
        max_wind_force_bft: Maximum wind force constraint.
        max_precipitation: Maximum precipitation description.
        expertise_level: Required expertise level, if any.
        wbc: WBC flag.
        fiets: Bicycle required flag.
        hub: HUB flag.
        dvp: DvP flag.
        sleutel: Key required flag.
        remarks_planning: Planner remarks.
        remarks_field: Field remarks.
        priority: Priority flag.
        part_of_day: Optional part-of-day helper.
        start_time_text: Human-readable start time description.
        preferred_researcher_id: Optional preferred researcher id.
        preferred_researcher: Compact preferred researcher representation.
        researchers: Assigned researchers for the visit.
    """

    id: int
    project_code: str
    project_location: str
    project_google_drive_folder: str | None = None
    cluster_id: int
    cluster_number: int
    cluster_address: str
    status: VisitStatusCode
    function_ids: list[int]
    species_ids: list[int]
    functions: list[FunctionCompactRead] = []
    species: list[SpeciesCompactRead] = []
    required_researchers: int | None
    visit_nr: int | None
    planned_week: int | None = None
    from_date: date | None
    to_date: date | None
    duration: int | None
    execution_date: date | None = None
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
    part_of_day: str | None = None
    start_time_text: str | None = None
    preferred_researcher_id: int | None = None
    preferred_researcher: UserNameRead | None = None
    researchers: list[UserNameRead] = []
    advertized: bool
    quote: bool
    advertized_by: UserNameRead | None = None
    can_accept: bool | None = None


class VisitListResponse(BaseModel):
    """Paginated response model for the visits overview listing.

    Attributes:
        items: Current page of flattened visit rows.
        total: Total number of visits matching the filters.
        page: 1-based page index.
        page_size: Number of items per page.
    """

    items: list[VisitListRow]
    total: int
    page: int
    page_size: int


class VisitCancelRequest(BaseModel):
    """Payload for cancelling a visit.

    Args:
        reason: Required explanation for the cancellation decision.
    """

    reason: str

from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel


class PlanningVisitRead(BaseModel):
    """Lightweight read model for planned visits used by the planning UI.

    Attributes:
        id: Visit id.
        project_code: Parent project short code.
        cluster_number: Cluster number within project.
        functions: Function names for the visit.
        species: Species names for the visit.
        from_date: Start of the visit window.
        to_date: End of the visit window.
        researchers: Assigned researcher display names.
    """

    id: int
    project_code: str
    cluster_number: str
    functions: list[str]
    species: list[str]
    from_date: date | None = None
    to_date: date | None = None
    planned_date: date | None = None
    researchers: list[str]

    model_config = {"from_attributes": True}


class PlanningGenerateRequest(BaseModel):
    """Request body for generating planning for a specific ISO week.

    Attributes:
        week: ISO week number (1-53) of the current year.
    """

    week: int


class SeasonPlannerStatusRead(BaseModel):
    """Season planner status metadata for admin UI.

    Args:
        last_run_at: Timestamp of the most recent season planner run.
    """

    last_run_at: datetime | None = None


class PlanningDiagnosticDetail(BaseModel):
    """Enriched planning diagnostic entry for admin dashboard.

    Combines a planning-season ActivityLog entry with the associated
    visit, cluster and project details so the admin UI can surface
    actionable warnings without a second API call.

    Args:
        visit_id: Id of the visit that could not be scheduled.
        action: Diagnostic action code (e.g. "planning_season_unscheduled").
        reason_nl: Human-readable Dutch explanation of why the visit failed.
        reason_code: Machine-readable reason code (e.g. "protocol_gap_infeasible").
        cluster_id: Id of the cluster owning the visit.
        cluster_number: Human-readable cluster identifier.
        project_code: Short code of the parent project.
        project_location: Location label of the parent project.
        visit_nr: Sequential visit number within the cluster.
        from_date: Start of the visit execution window.
        to_date: End of the visit execution window.
    """

    visit_id: int
    action: str
    reason_nl: str
    reason_code: str | None = None
    cluster_id: int | None = None
    cluster_number: str | None = None
    project_code: str | None = None
    project_location: str | None = None
    visit_nr: int | None = None
    from_date: date | None = None
    to_date: date | None = None

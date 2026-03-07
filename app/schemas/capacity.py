from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class FamilyDaypartCapacity(BaseModel):
    """Capacity cell for a single family, week and part of day.

    Attributes:
        required: Total number of researcher slots required for the
            family in this week and part of day.
        assigned: Number of required slots that could be assigned based
            on researcher qualifications and availability.
        shortfall: Difference between required and assigned. Always
            non-negative, where a positive value indicates unmet demand.
    """

    required: int
    assigned: int
    shortfall: int
    spare: int = 0


class WeekResultCell(BaseModel):
    spare: int
    planned: int
    shortage: int = 0


class WeekView(BaseModel):
    weeks: list[str]
    # Label -> Week -> Cell
    rows: dict[str, dict[str, WeekResultCell]]


class UnschedulableVisitInfo(BaseModel):
    """A visit that could not be scheduled, with a reason."""

    visit_id: int
    reason_nl: str
    reason_code: str
    # Display fields (populated when visit object is available)
    project_code: str | None = None
    cluster_address: str | None = None
    to_date: date | None = None
    part_of_day: str | None = None
    family: str | None = None


class DeadlineSummaryRow(BaseModel):
    """Aggregated visit counts per family, part-of-day and deadline date.

    Attributes:
        family: Researcher skill/family group (e.g. "Vleermuiskundige").
        part_of_day: Part of day (e.g. "Ochtend", "Avond").
        deadline: Visit end date (to_date), or None if no deadline.
        planned: Number of visits with a planned_week set.
        provisional: Number of visits with only a provisional_week set.
        not_scheduled: Number of visits with neither.
    """

    family: str
    part_of_day: str
    deadline: date | None
    planned: int
    provisional: int
    not_scheduled: int


class CapacitySimulationResponse(BaseModel):
    """Response model for long-term family capacity simulations.

    Attributes:
        horizon_start: First Monday included in the simulation horizon.
        horizon_end: Last Monday included in the simulation horizon.
        grid: (Legacy/Deadline) Nested mapping of Family name to Part-of-day label to
            Deadline Week (ISO week e.g. "2025-W48").
            Each leaf value is a :class:`FamilyDaypartCapacity`.
        week_view: Optional new view grouped by execution week.
        unschedulable_visits: Visits that could not be scheduled, with reasons.
            Populated from live diagnostics (simulate=true) or last solver run.
    """

    horizon_start: date
    horizon_end: date
    created_at: datetime | None = None
    updated_at: datetime | None = None
    grid: dict[str, dict[str, dict[str, FamilyDaypartCapacity]]]
    week_view: WeekView | None = None
    unschedulable_visits: list[UnschedulableVisitInfo] = []
    deadline_summary: list[DeadlineSummaryRow] = []

    model_config = {"from_attributes": True}

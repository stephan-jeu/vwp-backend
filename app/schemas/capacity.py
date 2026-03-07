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

    model_config = {"from_attributes": True}

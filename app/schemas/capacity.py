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
    demand: int = 0  # raw uncapped demand; equals planned when no overbooking
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


class BottleneckPeriod(BaseModel):
    """Consecutive weeks where extra capacity would let more visits be planned.

    Attributes:
        from_week: First ISO week of the period (e.g. "2026-W20").
        to_week: Last ISO week of the period.
        skills: Skills for which extra researcher-days in this period help.
        unmet_days: Researcher-days of visits for these skills that do not fit,
            with an execution window overlapping this period (indicative).
    """

    from_week: str
    to_week: str
    skills: list[str]
    unmet_days: int


class CapacityBottleneckReport(BaseModel):
    """Capacity check independent of the weeks the season planner chose.

    Attributes:
        total_unmet_days: Researcher-days that cannot be planned in any week,
            whatever the planning. A lower bound: protocol gaps between visits
            are not taken into account.
        unscheduled_visits: Visits the season planner could not fit in the
            capacity in its last run (None when unknown).
        unscheduled_days: Researcher-days of those visits. Unlike
            total_unmet_days this includes the minimum period between visits, so
            it is the more realistic number.
        committed_overbooked_days: Part of the shortage in visits already fixed
            to an overbooked week (planned, locked or custom); moving other
            visits cannot solve this.
        committed_overbooked_visits: Number of those visits (indicative).
        week_skills: ISO week -> skills that are a real bottleneck that week.
        periods: Bottleneck weeks grouped into consecutive periods.
    """

    total_unmet_days: int
    unscheduled_visits: int | None = None
    unscheduled_days: int | None = None
    committed_overbooked_days: int = 0
    committed_overbooked_visits: int = 0
    week_skills: dict[str, list[str]] = {}
    periods: list[BottleneckPeriod] = []


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
    bottlenecks: CapacityBottleneckReport | None = None

    model_config = {"from_attributes": True}

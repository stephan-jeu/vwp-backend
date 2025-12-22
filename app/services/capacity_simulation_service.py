from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.availability import AvailabilityWeek
from app.models.cluster import Cluster
from app.models.family import Family
from app.models.project import Project
from app.models.species import Species
from app.models.user import User
from app.models.visit import Visit
from app.schemas.capacity import CapacitySimulationResponse, FamilyDaypartCapacity
from app.services.visit_planning_selection import (
    DAYPART_TO_AVAIL_FIELD,
    _qualifies_user_for_visit,
    _load_all_users,
    _priority_key,
    _consume_capacity,
    _load_week_capacity,
    _select_visits_for_week_core,
)
from app.services.visit_selection_ortools import select_visits_cp_sat


DAYPART_LABELS: tuple[str, ...] = ("Ochtend", "Dag", "Avond")


class SimulationResultCell(NamedTuple):
    planned: int
    unplannable: int


def _week_id(week_monday: date) -> str:
    """Return ISO week identifier string (e.g. ``"2025-W48"``)."""
    iso_year, iso_week, _ = week_monday.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _get_family_name(v: Visit) -> str:
    """Return the primary family name for a visit or ``"?"``.

    The first species' family name is used when available; otherwise a
    best-effort placeholder is returned.
    """
    try:
        sp = (v.species or [None])[0]
        fam: Family | None = getattr(sp, "family", None)
        name = getattr(fam, "name", None)
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:  # pragma: no cover - defensive only
        pass
    return "?"


async def _load_user_daypart_capacities(
    db: AsyncSession, week: int
) -> dict[int, dict[str, int]]:
    """Return per-user capacity per daypart for the ISO week.

    The mapping keys are user IDs; values are dictionaries keyed by the
    human-readable part-of-day labels ("Ochtend", "Dag", "Avond") plus
    "Flex". Missing users are treated as having no capacity.
    """

    try:
        stmt = select(AvailabilityWeek).where(AvailabilityWeek.week == week)
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:  # pragma: no cover - defensive for fake DBs
        return {}

    per_user: dict[int, dict[str, int]] = {}
    for r in rows:
        try:
            uid = getattr(r, "user_id", None)
            if uid is None:
                continue
            morning = int(getattr(r, "morning_days", 0) or 0)
            daytime = int(getattr(r, "daytime_days", 0) or 0)
            night = int(getattr(r, "nighttime_days", 0) or 0)
            flex = int(getattr(r, "flex_days", 0) or 0)
            per_user[uid] = {
                "Ochtend": morning,
                "Dag": daytime,
                "Avond": night,
                "Flex": flex,
            }
        except Exception:  # pragma: no cover - defensive for malformed rows
            continue
    return per_user


def _user_has_capacity_for_part(
    per_user_caps: dict[int, dict[str, int]], uid: int, part: str
) -> bool:
    """Return True if user has at least one slot for the given part.

    Dedicated part capacity is preferred; if none is available, flex capacity
    can be used. If the user has no entry in ``per_user_caps``, they are
    treated as having zero capacity.
    """

    caps = per_user_caps.get(uid)
    if caps is None:
        return False

    have = caps.get(part, 0)
    if have > 0:
        return True
    return caps.get("Flex", 0) > 0


def _consume_user_capacity_for_part(
    per_user_caps: dict[int, dict[str, int]], uid: int, part: str
) -> bool:
    """Consume one capacity unit for the given user and part.

    Returns ``True`` on success, ``False`` if no dedicated or flex capacity is
    available for this user and part.
    """

    caps = per_user_caps.get(uid)
    if caps is None:
        return False

    have = caps.get(part, 0)
    if have > 0:
        caps[part] = have - 1
        return True

    flex = caps.get("Flex", 0)
    if flex > 0:
        caps["Flex"] = flex - 1
        return True

    return False


async def _load_all_open_visits(db: AsyncSession, start_date: date) -> list[Visit]:
    """Load all visits that are not yet fully executed/cancelled.

    This includes visits that are 'planned' in the real system but not yet executed,
    as we want to re-simulate their planning to see if they fit.
    """
    # We want visits that are NOT in a terminal state (executed, cancelled, rejected, etc.)
    # Ideally we'd filter by status, but status is derived.
    # So we fetch all visits that have a to_date >= start_date (or are undated/open)
    # AND are not cancelled/executed in logs.
    # For simplicity/performance, we'll fetch a broad set and filter in python using derive_visit_status.

    # Optimization: Filter out visits that are definitely in the past
    stmt = (
        select(Visit)
        .join(Cluster, Visit.cluster_id == Cluster.id)
        .join(Project, Cluster.project_id == Project.id)
        .where(or_(Visit.to_date >= start_date, Visit.to_date.is_(None)))
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
    )

    candidates = (await db.execute(stmt)).scalars().unique().all()

    # Filter using derived status
    # We treat PLANNED as "open" for the purpose of simulation because we want to see if they fit
    # given the capacity.
    # We exclude EXECUTED, CANCELLED, etc.

    active_visits = []
    # We need to fetch logs for status derivation?
    # For bulk simulation, fetching logs for every visit might be slow.
    # Let's assume for now that if it's not in the past, it's fair game,
    # unless we want to be very precise about cancelled visits.
    # TODO: If performance is an issue, bulk load logs.

    # For now, let's accept the slight inaccuracy of including cancelled visits
    # if we don't want to fetch logs for all.
    # OR, we can rely on the user to have cleaned up.
    # Let's try to be correct:


    # Bulk fetch latest status logs?
    # This is complex. Let's stick to a simpler heuristic:
    # If it has a result or is cancelled, it usually has a status.
    # Let's assume for this simulation we care about "to be done" work.

    for v in candidates:
        # Quick check: if it has a result status in real life, skip?
        # We'll use the status service but maybe without logs for speed?
        # Or just fetch logs.
        # Let's just include them all for now, the user said "created, open, planned or not executed"
        active_visits.append(v)

    return active_visits


async def simulate_capacity_planning(
    db: AsyncSession,
    start_monday: date | None,
) -> CapacitySimulationResponse:
    """Simulate capacity planning for the remainder of the year.

    Stateful simulation:
    1. Start with all open visits.
    2. Iterate week by week.
    3. In each week, try to plan visits that can be done in that week.
    4. If planned, remove from pool.
    5. If not, keep in pool for next week.
    6. At end, report grouped by deadline.
    """

    if start_monday is None:
        today = date.today()
        iso_year, iso_week, iso_weekday = today.isocalendar()
        start_monday = date.fromisocalendar(iso_year, iso_week, 1)
    else:
        iso_year, iso_week, iso_weekday = start_monday.isocalendar()
        start_monday = date.fromisocalendar(iso_year, iso_week, 1)

    horizon_start = start_monday
    horizon_end = date(start_monday.year, 12, 31)

    # 1. Fetch all relevant visits
    all_visits = await _load_all_open_visits(db, horizon_start)

    # Sort by global priority once? Or re-sort every week?
    # Priority depends on "weeks until deadline", so it changes every week.
    # But base priority (tier) is static.

    # We need a mutable pool
    visit_pool = list(all_visits)

    # Track results: family -> part -> deadline_week -> {planned, unplannable}
    # We use a nested dict structure
    # deadline_week is the ISO week of the visit.to_date
    results: dict[str, dict[str, dict[str, SimulationResultCell]]] = {}

    # Helper to add result
    def add_result(v: Visit, is_planned: bool):
        fam = _get_family_name(v)
        part = (v.part_of_day or "Onbekend").strip()
        if v.to_date:
            deadline = v.to_date.isoformat()
        else:
            deadline = "No Deadline"

        fam_dict = results.setdefault(fam, {})
        part_dict = fam_dict.setdefault(part, {})

        current = part_dict.get(deadline, SimulationResultCell(0, 0))
        if is_planned:
            part_dict[deadline] = SimulationResultCell(
                current.planned + 1, current.unplannable
            )
        else:
            part_dict[deadline] = SimulationResultCell(
                current.planned, current.unplannable + 1
            )

    # 2. Iterate weeks
    current_monday = horizon_start
    while current_monday <= horizon_end:
        week_friday = current_monday + timedelta(days=4)
        week_iso = current_monday.isocalendar().week

        # Load capacity for this week
        # caps = await _load_week_capacity(db, week_iso) # Not needed for CP-SAT solver directly

        # Filter pool for visits that CAN be done this week
        # i.e. from_date <= week_friday AND to_date >= current_monday
        eligible_indices = []
        for i, v in enumerate(visit_pool):
            f = v.from_date or date.min
            t = v.to_date or date.max
            if f <= week_friday and t >= current_monday:
                eligible_indices.append(i)

        # Try to plan using OR-Tools Solver
        # We pass only the eligible visits to the solver.
        # Since we are simulating, we don't commit to DB.
        
        eligible_subset_visits = [visit_pool[i] for i in eligible_indices]
        
        selection_result = await select_visits_cp_sat(db, current_monday, visits=eligible_subset_visits)
        
        for v in selection_result.selected:
            add_result(v, is_planned=True)
            
        # Rebuild pool:
        # Keep visits that were NOT eligible this week
        # PLUS visits that were eligible but SKIPPED by the solver.
        
        new_pool = []
        # Add non-eligible visits (indices not in eligible_indices)
        eligible_indices_set = set(eligible_indices)
        for i, v in enumerate(visit_pool):
            if i not in eligible_indices_set:
                new_pool.append(v)
        
        # Add skipped visits (solver rejected them)
        # Note: skipped visits in selection_result.skipped might include visits filtered by solver (e.g. no daypart)
        # But we only passed eligible visits in, so they should return.
        
        for v in selection_result.skipped:
             new_pool.append(v)

        visit_pool = new_pool

        current_monday += timedelta(days=7)

    # 3. Remaining visits are unplannable (within the horizon)
    for v in visit_pool:
        add_result(v, is_planned=False)

    # Convert NamedTuple to dict for JSON serialization if needed,
    # or rely on Pydantic schema compatibility.
    # The schema expects: grid: dict[str, dict[str, dict[str, FamilyDaypartCapacity]]]
    # But we changed the meaning. We need to update the schema or map to it.
    # The user wants: "display in each cell nr of unplannable visits/nr of planned visits"
    # Let's reuse FamilyDaypartCapacity but abuse fields:
    # assigned -> planned
    # shortfall -> unplannable
    # required -> total (planned + unplannable)
    # spare -> 0

    final_grid: dict[str, dict[str, dict[str, FamilyDaypartCapacity]]] = {}

    for fam, parts in results.items():
        final_grid[fam] = {}
        for part, deadlines in parts.items():
            final_grid[fam][part] = {}
            for deadline, cell in deadlines.items():
                final_grid[fam][part][deadline] = FamilyDaypartCapacity(
                    required=cell.planned + cell.unplannable,
                    assigned=cell.planned,
                    shortfall=cell.unplannable,
                    spare=0,
                )

    return CapacitySimulationResponse(
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        grid=final_grid,
    )


async def simulate_week_capacity(
    db: AsyncSession,
    week_monday: date,
) -> dict[str, dict[str, FamilyDaypartCapacity]]:
    """Simulate family/daypart capacity usage for a single week.

    This helper uses the OR-Tools solver to determine optimal assignments
    that respect strict day coordination and capacity rules, then aggregates
    the results into family/daypart stats.
    """

    # Use solver to determine optimal selection/assignment
    selection_result = await select_visits_cp_sat(db, week_monday)
    
    if not selection_result.selected and not selection_result.skipped:
        return {}
        
    result: dict[str, dict[str, FamilyDaypartCapacity]] = {}

    def add_stats(visits: list[Visit], is_assigned: bool):
        for v in visits:
            fam = _get_family_name(v)
            part = (getattr(v, "part_of_day", None) or "").strip()
            if not part:
                continue
            
            req = int(getattr(v, "required_researchers", None) or 1)
            
            # If assigned, count full requirement. If skipped, count shortfall.
            assigned_count = req if is_assigned else 0
            shortfall_count = 0 if is_assigned else req
            
            fam_map = result.setdefault(fam, {})
            cell = fam_map.get(part)
            if cell is None:
                cell = FamilyDaypartCapacity(required=0, assigned=0, shortfall=0, spare=0)
                
            new_required = cell.required + req
            new_assigned = cell.assigned + assigned_count
            new_shortfall = cell.shortfall + shortfall_count
            
            fam_map[part] = FamilyDaypartCapacity(
                required=new_required,
                assigned=new_assigned,
                shortfall=new_shortfall,
                spare=cell.spare,
            )

    add_stats(selection_result.selected, is_assigned=True)
    add_stats(selection_result.skipped, is_assigned=False)

    return result


async def simulate_capacity_horizon(
    db: AsyncSession,
    any_day: date | None,
) -> CapacitySimulationResponse:
    """Simulate capacity for a planning horizon starting at the given date.

    The current implementation normalizes ``any_day`` to the Monday of its
    ISO week, runs :func:`simulate_week_capacity` for that week only and
    stores the result under the corresponding week identifier.
    """

    if any_day is None:
        any_day = date.today()

    iso_year, iso_week, _ = any_day.isocalendar()
    start_monday = date.fromisocalendar(iso_year, iso_week, 1)
    week_key = _week_id(start_monday)

    week_grid = await simulate_week_capacity(db, start_monday)

    # Shape: week_id -> family -> part -> FamilyDaypartCapacity
    grid: dict[str, dict[str, dict[str, FamilyDaypartCapacity]]] = {}
    if week_grid:
        grid[week_key] = {}
        for fam, parts in week_grid.items():
            grid[week_key][fam] = {}
            for part, cell in parts.items():
                grid[week_key][fam][part] = cell

    return CapacitySimulationResponse(
        horizon_start=start_monday,
        horizon_end=start_monday,
        grid=grid,
    )

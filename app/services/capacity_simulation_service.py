from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.availability import AvailabilityWeek
from app.models.family import Family
from app.models.user import User
from app.models.visit import Visit
from app.schemas.capacity import CapacitySimulationResponse, FamilyDaypartCapacity
from app.services.visit_planning_selection import (
    DAYPART_TO_AVAIL_FIELD,
    _qualifies_user_for_visit,
    _select_visits_for_week_core,
    _load_all_users,
)


DAYPART_LABELS: tuple[str, ...] = ("Ochtend", "Dag", "Avond")


async def _load_user_daypart_capacity(
    db: AsyncSession, week: int
) -> dict[int, dict[str, int]]:
    """Return per-user capacity buckets for the ISO week.

    Capacity is expressed in the same units as availability (days) and is
    split per part-of-day plus a separate flex bucket.

    Args:
        db: Async SQLAlchemy session.
        week: ISO week number (1-53).

    Returns:
        Mapping ``user_id -> {"Ochtend"|"Dag"|"Avond"|"Flex": days}``.
    """

    caps: dict[int, dict[str, int]] = {}

    rows = (
        (
            await db.execute(
                AvailabilityWeek.__table__.select().where(AvailabilityWeek.week == week)
            )
        )
        .scalars()
        .all()
    )

    for row in rows:
        uid = getattr(row, "user_id", None)
        if uid is None:
            continue
        caps[uid] = {
            "Ochtend": int(getattr(row, "morning_days", 0) or 0),
            "Dag": int(getattr(row, "daytime_days", 0) or 0),
            "Avond": int(getattr(row, "nighttime_days", 0) or 0),
            "Flex": int(getattr(row, "flex_days", 0) or 0),
        }

    return caps


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


async def simulate_week_capacity(
    db: AsyncSession,
    week_monday: date,
) -> dict[str, dict[str, FamilyDaypartCapacity]]:
    """Simulate capacity usage per family and daypart for a single week.

    This uses the same visit selection core as the planner to determine
    which visits are in scope for the week. It then simulates researcher
    assignment in-memory using per-user availability from
    :class:`AvailabilityWeek`, popping capacity buckets without writing
    any changes to the database.

    Args:
        db: Async SQLAlchemy session.
        week_monday: Monday date of the work week to simulate.

    Returns:
        Nested mapping of ``family_name -> part_of_day -> cell`` for the
        specified week.
    """

    selected, _skipped, _caps = await _select_visits_for_week_core(db, week_monday)

    if not selected:
        return {}

    week = week_monday.isocalendar().week
    user_caps = await _load_user_daypart_capacity(db, week)
    users: list[User] = await _load_all_users(db)

    # Running tally of how many slots each user has been assigned in this week
    assigned_slots_total: dict[int, int] = {}

    # demand and assignment per family/part-of-day
    required: dict[str, dict[str, int]] = {}
    assigned: dict[str, dict[str, int]] = {}

    for visit in selected:
        part = (getattr(visit, "part_of_day", None) or "").strip()
        if part not in DAYPART_TO_AVAIL_FIELD:
            logger.warning(
                "capacity_simulation skip visit id=%s due to unknown part_of_day=%s",
                getattr(visit, "id", None),
                part or None,
            )
            continue

        fam_name = _get_family_name(visit)
        needed = max(1, getattr(visit, "required_researchers", 1) or 1)

        fam_required = required.setdefault(fam_name, {})
        fam_required[part] = fam_required.get(part, 0) + needed

        fam_assigned = assigned.setdefault(fam_name, {})

        # Build list of currently eligible users
        eligible_users: list[User] = []
        for user in users:
            uid = getattr(user, "id", None)
            if uid is None:
                continue
            caps = user_caps.get(uid)
            if not caps:
                continue
            if caps.get(part, 0) <= 0 and caps.get("Flex", 0) <= 0:
                continue
            if not _qualifies_user_for_visit(user, visit):
                continue
            eligible_users.append(user)

        for _slot in range(needed):
            # Re-sort for each slot so that we always pick the user with the
            # lowest total assigned slots, then lowest user id.
            eligible_users.sort(
                key=lambda u: (
                    assigned_slots_total.get(getattr(u, "id", 0), 0),
                    getattr(u, "id", 0),
                )
            )

            chosen: User | None = None
            for user in eligible_users:
                uid = getattr(user, "id", None)
                if uid is None:
                    continue
                caps = user_caps.get(uid)
                if not caps:
                    continue
                if caps.get(part, 0) > 0 or caps.get("Flex", 0) > 0:
                    chosen = user
                    break

            if chosen is None:
                # No remaining qualified capacity for this slot
                continue

            uid = getattr(chosen, "id", None)
            if uid is None:
                continue

            caps = user_caps.get(uid, {})
            if caps.get(part, 0) > 0:
                caps[part] = caps.get(part, 0) - 1
            elif caps.get("Flex", 0) > 0:
                caps["Flex"] = caps.get("Flex", 0) - 1
            else:  # pragma: no cover - defensive only
                continue

            user_caps[uid] = caps
            assigned_slots_total[uid] = assigned_slots_total.get(uid, 0) + 1

            fam_assigned[part] = fam_assigned.get(part, 0) + 1

    # Build FamilyDaypartCapacity cells
    result: dict[str, dict[str, FamilyDaypartCapacity]] = {}
    for fam_name, parts_required in required.items():
        parts_assigned = assigned.get(fam_name, {})
        fam_cells: dict[str, FamilyDaypartCapacity] = {}
        for part, req_value in parts_required.items():
            asg_value = parts_assigned.get(part, 0)
            shortfall = max(0, req_value - asg_value)
            fam_cells[part] = FamilyDaypartCapacity(
                required=req_value,
                assigned=asg_value,
                shortfall=shortfall,
            )
        result[fam_name] = fam_cells

    return result


async def simulate_capacity_horizon(
    db: AsyncSession,
    start_monday: date | None,
) -> CapacitySimulationResponse:
    """Simulate capacity for all weeks from start to end of year.

    Args:
        db: Async SQLAlchemy session.
        start_monday: Optional Monday date to start the simulation on.
            If ``None``, the Monday of the current calendar week is used.

    Returns:
        Aggregated capacity grid for the remainder of the year.
    """

    if start_monday is None:
        today = date.today()
        iso_year, iso_week, iso_weekday = today.isocalendar()
        start_monday = date.fromisocalendar(iso_year, iso_week, 1)
    else:
        iso_year, iso_week, iso_weekday = start_monday.isocalendar()
        # Normalize to Monday of the same ISO week
        start_monday = date.fromisocalendar(iso_year, iso_week, 1)

    horizon_start = start_monday
    horizon_end = date(start_monday.year, 12, 31)

    grid: dict[str, dict[str, dict[str, FamilyDaypartCapacity]]] = {}

    week_monday = horizon_start
    while week_monday <= horizon_end:
        week_key = _week_id(week_monday)
        week_data = await simulate_week_capacity(db, week_monday)
        if week_data:
            grid[week_key] = week_data
        week_monday += timedelta(days=7)

    return CapacitySimulationResponse(
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        grid=grid,
    )

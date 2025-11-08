from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable
import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.visit import Visit
from app.models.species import Species
from app.models.family import Family
from app.models.function import Function
from app.models.availability import AvailabilityWeek


_logger = logging.getLogger("uvicorn.error")


DAYPART_TO_AVAIL_FIELD = {
    "Ochtend": "morning_days",
    "Dag": "daytime_days",
    "Avond": "nighttime_days",
}

SPARE_BY_DAYPART = {
    "Ochtend": 1,
    "Dag": 2,
    "Avond": 2,
}


def _end_of_work_week(week_monday: date) -> date:
    return week_monday + timedelta(days=4)


def _first_function_name(v: Visit) -> str:
    try:
        return (v.functions[0].name or "").strip()
    except Exception:
        return ""


def _any_function_contains(v: Visit, needles: Iterable[str]) -> bool:
    names = [(f.name or "").lower() for f in (v.functions or [])]
    return any(any(needle.lower() in n for n in names) for needle in needles)


def _family_priority_from_first_species(v: Visit) -> int | None:
    try:
        sp: Species = v.species[0]
        fam: Family | None = sp.family
        return getattr(fam, "priority", None)
    except Exception:
        return None


def _priority_key(week_monday: date, v: Visit) -> tuple:
    # Build priority tiers as boolean flags (True = matches tier). Sort by descending flags.
    two_weeks_after_monday = week_monday + timedelta(days=14)

    tier1 = bool(v.priority)
    tier2 = bool(v.to_date and v.to_date <= two_weeks_after_monday)
    fam_prio = _family_priority_from_first_species(v)
    tier3 = bool(fam_prio is not None and fam_prio <= 3)
    fn0 = _first_function_name(v)
    tier4 = fn0.startswith("SMP")
    tier5 = _any_function_contains(v, ("Vliegroute", "Foerageergebied"))
    tier6 = bool(v.hup)
    tier7 = bool(getattr(v, "sleutel", False))
    tier8 = bool(v.fiets or v.dvp or v.wbc)

    # Stable sort within tiers by (earlier to_date first, then earlier from_date, then id)
    stable = (
        (v.to_date or date.max),
        (v.from_date or date.max),
        v.id or 0,
    )
    # Negate tiers to sort True before False
    return tuple(int(t) for t in (
        tier1, tier2, tier3, tier4, tier5, tier6, tier7, tier8
    ))[::-1], stable


async def _load_week_capacity(db: AsyncSession, week: int) -> dict:
    stmt = select(AvailabilityWeek).where(AvailabilityWeek.week == week)
    rows = (await db.execute(stmt)).scalars().all()

    total_morning = sum(r.morning_days or 0 for r in rows)
    total_daytime = sum(r.daytime_days or 0 for r in rows)
    total_night = sum(r.nighttime_days or 0 for r in rows)
    total_flex = sum(r.flex_days or 0 for r in rows)

    # Apply spare capacity caps (cannot go below zero)
    total_morning = max(0, total_morning - SPARE_BY_DAYPART["Ochtend"])
    total_daytime = max(0, total_daytime - SPARE_BY_DAYPART["Dag"])
    total_night = max(0, total_night - SPARE_BY_DAYPART["Avond"])

    return {
        "Ochtend": total_morning,
        "Dag": total_daytime,
        "Avond": total_night,
        "Flex": total_flex,
    }


async def _eligible_visits_for_week(db: AsyncSession, week_monday: date) -> list[Visit]:
    week_friday = _end_of_work_week(week_monday)

    stmt = (
        select(Visit)
        .where(
            and_(
                Visit.from_date <= week_friday,
                Visit.to_date >= week_monday,
            )
        )
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
        )
    )
    return (await db.execute(stmt)).scalars().unique().all()


def _consume_capacity(caps: dict, part: str, required: int) -> bool:
    # Try dedicated part capacity first
    have = caps.get(part, 0)
    if have >= required:
        caps[part] = have - required
        return True
    # Use flex to cover the shortfall
    short = required - max(0, have)
    flex = caps.get("Flex", 0)
    # consume remaining dedicated then flex
    used_dedicated = min(required, have)
    caps[part] = max(0, have - used_dedicated)
    if flex >= short:
        caps["Flex"] = flex - short
        return True
    # not enough capacity; revert dedicated change
    caps[part] = have
    return False


def _format_visit_line(v: Visit) -> str:
    fnames = ", ".join(sorted({(f.name or "").strip() for f in (v.functions or [])}))
    snames = ", ".join(sorted({(s.name or "").strip() for s in (v.species or [])}))
    pod = v.part_of_day or "?"
    req = v.required_researchers or 1
    return (
        f"- Functions: [{fnames}] | Species: [{snames}] | "
        f"From: {getattr(v, 'from_date', None)} To: {getattr(v, 'to_date', None)} | "
        f"Part: {pod} | Required researchers: {req} | Assigned researchers: []"
    )


async def select_visits_for_week(db: AsyncSession, week_monday: date) -> dict:
    """Select visits for the given work week (Mon–Fri) according to business rules.

    Selection respects weekly capacity per daypart (minus spare) and uses flex to
    cover deficits. No per-day simulation and no researcher qualification matching
    in this phase. Returns a structured summary and logs a human-readable list.
    """

    week = week_monday.isocalendar().week
    caps = await _load_week_capacity(db, week)

    visits = await _eligible_visits_for_week(db, week_monday)

    # Sort by priority tiers
    visits_sorted = sorted(
        visits,
        key=lambda v: _priority_key(week_monday, v),
        reverse=True,
    )

    selected: list[Visit] = []
    skipped: list[Visit] = []

    for v in visits_sorted:
        part = (v.part_of_day or "").strip()
        if part not in DAYPART_TO_AVAIL_FIELD:
            _logger.warning(
                "visit_select skip id=%s: unknown part_of_day=%s", getattr(v, "id", None), part or None
            )
            skipped.append(v)
            continue
        required = v.required_researchers or 1
        if _consume_capacity(caps, part, required):
            selected.append(v)
        else:
            skipped.append(v)

    # Log output
    if selected:
        _logger.info("Selected visits for week starting %s:", week_monday.isoformat())
        for v in selected:
            _logger.info(_format_visit_line(v))
    else:
        _logger.info("No visits selected for week starting %s", week_monday.isoformat())

    return {
        "selected_visit_ids": [v.id for v in selected],
        "skipped_visit_ids": [v.id for v in skipped],
        "capacity_remaining": caps,
    }

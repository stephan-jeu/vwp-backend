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
from app.models.user import User
from app.services import travel_time


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
    # Build priority tiers as boolean flags (True = matches tier). We want True > False
    # in the listed order. Compute a single integer weight where higher is better,
    # then sort by (-weight, to_date, from_date, id) to keep deterministic order.
    two_weeks_after_monday = week_monday + timedelta(days=14)

    tier1 = bool(v.priority)
    tier2 = bool(v.to_date and v.to_date <= two_weeks_after_monday)
    fam_prio = _family_priority_from_first_species(v)
    tier3 = bool(fam_prio is not None and fam_prio <= 3)
    fn0 = _first_function_name(v)
    tier4 = fn0.lstrip().upper().startswith("SMP")
    tier5 = _any_function_contains(v, ("Vliegroute", "Foerageergebied"))
    tier6 = bool(getattr(v, "hub", False))
    tier7 = bool(getattr(v, "sleutel", False))
    tier8 = bool(
        getattr(v, "fiets", False)
        or getattr(v, "dvp", False)
        or getattr(v, "wbc", False)
    )

    # Weight: tier1 most significant down to tier8 least; use bit shifts
    weight = (
        (int(tier1) << 7)
        | (int(tier2) << 6)
        | (int(tier3) << 5)
        | (int(tier4) << 4)
        | (int(tier5) << 3)
        | (int(tier6) << 2)
        | (int(tier7) << 1)
        | int(tier8)
    )

    # Stable tie-breakers: earlier dates first, then smaller id
    to_d = v.to_date or date.max
    from_d = v.from_date or date.max
    vid = v.id or 0

    return (-weight, to_d, from_d, vid)


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
            selectinload(Visit.researchers),
            selectinload(Visit.cluster),
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
    assigned = [
        getattr(u, "full_name", "") or "" for u in (getattr(v, "researchers", []) or [])
    ]
    return (
        f"- Functions: [{fnames}] | Species: [{snames}] | "
        f"From: {getattr(v, 'from_date', None)} To: {getattr(v, 'to_date', None)} | "
        f"Part: {pod} | Required researchers: {req} | Assigned researchers: {assigned}"
    )


def _qualifies_user_for_visit(user: User, visit: Visit) -> bool:
    """Return True if user qualifies for the given visit based on rules.

    Rules:
    - User must qualify for ALL families of the visit's species.
    - If first function starts with SMP (case-insensitive, leading spaces allowed), user.smp must be True.
    - If any function contains 'Vliegroute' or 'Foerageergebied' (case-insensitive), user.vrfg must be True.
    - If visit.hub/fiets/wbc/dvp/sleutel is True, the corresponding user boolean must be True.
    """
    # Family -> user attribute mapping
    fam_to_user_attr = {
        "biggenkruid": "biggenkruid",
        "langoren": "langoor",
        "pad": "pad",
        "roofvogel": "roofvogel",
        "schijfhoren": "schijfhoren",
        "vleermuis": "vleermuis",
        "grote vos": "grote_vos",
        "iepenpage": "iepenpage",
        "teunisbloempijlstaart": "teunisbloempijlstaart",
        "zangvogel": "zangvogel",
        "zwaluw": "zwaluw",
    }

    # SMP specialization: if visit is SMP, require the appropriate SMP flag and skip
    # base family qualification enforcement. This means smp_* alone suffices for SMP visits.
    is_smp = _first_function_name(visit).lstrip().upper().startswith("SMP")
    smp_ok = False
    if is_smp:
        sp = (visit.species or [None])[0]
        fam_name = str(getattr(getattr(sp, "family", None), "name", "")).strip().lower()
        required_attr: str | None = None
        if fam_name == "vleermuis":
            required_attr = "smp_vleermuis"
        elif fam_name == "zwaluw":
            required_attr = "smp_gierzwaluw"
        elif fam_name == "zangvogel":
            required_attr = "smp_huismus"
        if required_attr is not None:
            smp_ok = bool(getattr(user, required_attr, False))
            if not smp_ok:
                return False
        else:
            _logger.warning(
                "Unknown SMP function %s for species %s with family %s. Could not assign visit. ",
                _first_function_name(visit),
                getattr(sp, "name", ""),
                fam_name,
            )
            return False

    # Family qualifications: user must have True for each family present, unless SMP
    # specialization was required and satisfied for this visit (then skip family checks).
    if not is_smp or not smp_ok:
        species_names_lower = [
            str(getattr(sp, "name", "")).strip().lower() for sp in (visit.species or [])
        ]
        for sp in visit.species or []:
            fam: Family | None = getattr(sp, "family", None)
            fam_name = getattr(fam, "name", None)
            key = (
                str(fam_name).strip().lower()
                if fam_name
                else str(getattr(sp, "name", "")).strip().lower()
            )
            attr = fam_to_user_attr.get(key)
            if attr and not bool(getattr(user, attr, False)):
                return False
        # Direct species name enforcement as an extra safety net
        for key, attr in fam_to_user_attr.items():
            if key in species_names_lower and not bool(getattr(user, attr, False)):
                return False

    # VRFG function rule
    if _any_function_contains(visit, ("Vliegroute", "Foerageergebied")):
        if not bool(getattr(user, "vrfg", False)):
            return False

    # Visit flags that must exist on user when required
    for flag in ("hub", "fiets", "wbc", "dvp", "sleutel"):
        if bool(getattr(visit, flag, False)) and not bool(getattr(user, flag, False)):
            return False

    return True


async def _load_all_users(db: AsyncSession) -> list[User]:
    """Load all users once. Extracted for easier monkeypatching in tests."""
    return (await db.execute(select(User))).scalars().all()


async def _load_user_capacities(db: AsyncSession, week: int) -> dict[int, int]:
    """Return per-user total capacity for the ISO week (sum of all dayparts + flex)."""
    try:
        stmt = select(AvailabilityWeek).where(AvailabilityWeek.week == week)
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        # In tests a fake DB may not support this; treat as no capacity info.
        return {}

    caps: dict[int, int] = {}
    for r in rows:
        try:
            uid = getattr(r, "user_id", None)
            if uid is None:
                continue
            total = (
                int(getattr(r, "morning_days", 0) or 0)
                + int(getattr(r, "daytime_days", 0) or 0)
                + int(getattr(r, "nighttime_days", 0) or 0)
                + int(getattr(r, "flex_days", 0) or 0)
            )
            caps[uid] = total
        except Exception:
            # Skip malformed rows from fakes
            continue
    return caps


def _bucketize_travel(minutes: int) -> int | None:
    if minutes < 0:
        return None
    if minutes <= 15:
        return 1
    if minutes <= 30:
        return 2
    if minutes <= 45:
        return 3
    if minutes <= 60:
        return 4
    if minutes <= 75:
        return 6
    return None  # excluded if >75


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
    )

    selected: list[Visit] = []
    skipped: list[Visit] = []

    for v in visits_sorted:
        part = (v.part_of_day or "").strip()
        if part not in DAYPART_TO_AVAIL_FIELD:
            _logger.warning(
                "visit_select skip id=%s: unknown part_of_day=%s",
                getattr(v, "id", None),
                part or None,
            )
            skipped.append(v)
            continue
        required = v.required_researchers or 1
        if _consume_capacity(caps, part, required):
            selected.append(v)
        else:
            skipped.append(v)

    # Assign researchers based on qualifications with weighted scoring
    if visits_sorted and db is not None:
        # Load users and capacities once
        users: list[User] = await _load_all_users(db)
        week = week_monday.isocalendar().week
        per_user_capacity: dict[int, int] = await _load_user_capacities(db, week)

        # Do not reuse users within this run to avoid double-booking within the week
        used_user_ids: set[int] = set()

        # Running tallies for ratios within this week's run
        assigned_count: dict[int, int] = {}
        assigned_heavy_count: dict[int, int] = {}
        assigned_fiets_count: dict[int, int] = {}
        assigned_by_project: dict[tuple[int, int], int] = (
            {}
        )  # (user_id, project_id) -> count

        # Precompute week-level denominators
        total_heavy_visits_week = sum(
            1 for x in selected if (x.required_researchers or 1) > 2
        )
        total_fiets_visits_week = sum(
            1 for x in selected if bool(getattr(x, "fiets", False))
        )
        visits_per_project_week: dict[int, int] = {}
        for x in selected:
            try:
                pid = getattr(getattr(x, "cluster", None), "project_id", None)
                if pid is not None:
                    visits_per_project_week[pid] = (
                        visits_per_project_week.get(pid, 0) + 1
                    )
            except Exception:
                pass

        for v in selected:
            needed = max(1, v.required_researchers or 1)
            # Filter qualifying and unused users first
            eligible = [
                u
                for u in users
                if (getattr(u, "id", None) not in used_user_ids)
                and _qualifies_user_for_visit(u, v)
            ]

            # Compute scores
            scored: list[tuple[float, User]] = []
            for u in eligible:
                uid = getattr(u, "id", None)
                if uid is None:
                    continue

                score_total = 0.0

                # 1) Travel time (weight 4); ignore on failure
                origin = (
                    getattr(u, "address", None) or getattr(u, "city", None) or ""
                ).strip()
                dest = (
                    getattr(getattr(v, "cluster", None), "address", None) or ""
                ).strip()
                if origin and dest:
                    minutes = await travel_time.get_travel_minutes(origin, dest)
                    if minutes is not None:
                        b = _bucketize_travel(minutes)
                        if b is None:
                            # Excluded due to >75 minutes
                            continue
                        travel_val = b / 6.0
                        score_total += travel_val * 4.0

                # 2) Already assigned / total available capacity (weight 3)
                already = assigned_count.get(uid, 0)
                capacity = max(0, per_user_capacity.get(uid, 0))
                ratio_assigned = (already / capacity) if capacity > 0 else 1.0
                score_total += ratio_assigned * 3.0

                # 3) Heavy visits ratio (weight 3)
                heavy_assigned = assigned_heavy_count.get(uid, 0)
                denom_heavy = total_heavy_visits_week
                ratio_heavy = (heavy_assigned / denom_heavy) if denom_heavy > 0 else 0.0
                score_total += ratio_heavy * 3.0

                # 4) Fiets ratio (weight 1)
                fiets_assigned = assigned_fiets_count.get(uid, 0)
                denom_fiets = total_fiets_visits_week
                ratio_fiets = (fiets_assigned / denom_fiets) if denom_fiets > 0 else 0.0
                score_total += ratio_fiets * 1.0

                # 5) Project familiarity ratio (weight 1) – same week window
                pid = getattr(getattr(v, "cluster", None), "project_id", None)
                proj_assigned = (
                    assigned_by_project.get((uid, pid), 0) if pid is not None else 0
                )
                proj_total = (
                    visits_per_project_week.get(pid, 0) if pid is not None else 0
                )
                ratio_proj = (proj_assigned / proj_total) if proj_total > 0 else 0.0
                score_total += ratio_proj * 1.0

                scored.append((score_total, u))

            # Pick lowest scores, tie-break by user id
            scored.sort(key=lambda t: (t[0], getattr(t[1], "id", 0)))
            take_users = [u for (_s, u) in scored[:needed]]

            if take_users:
                if getattr(v, "researchers", None) is None:
                    setattr(v, "researchers", [])
                for u in take_users:
                    v.researchers.append(u)
                    uid = getattr(u, "id", None)
                    if uid is not None:
                        used_user_ids.add(uid)
                        # update tallies
                        assigned_count[uid] = assigned_count.get(uid, 0) + 1
                        if (v.required_researchers or 1) > 2:
                            assigned_heavy_count[uid] = (
                                assigned_heavy_count.get(uid, 0) + 1
                            )
                        if bool(getattr(v, "fiets", False)):
                            assigned_fiets_count[uid] = (
                                assigned_fiets_count.get(uid, 0) + 1
                            )
                        pid = getattr(getattr(v, "cluster", None), "project_id", None)
                        if pid is not None:
                            key = (uid, pid)
                            assigned_by_project[key] = (
                                assigned_by_project.get(key, 0) + 1
                            )

        await db.commit()

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

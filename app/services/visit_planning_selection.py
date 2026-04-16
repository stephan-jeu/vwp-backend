from __future__ import annotations

import os
import random
import re
from datetime import date, timedelta
from typing import Iterable
import logging

from uuid import uuid4

from sqlalchemy import delete, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity_log import ActivityLog

from app.db.utils import select_active
from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.species import Species
from app.models.family import Family
from app.models.function import Function
from app.models.availability import AvailabilityWeek
from app.models.user import User
from app.services.visit_status_service import (
    VisitStatusCode,
    derive_visit_status,
    resolve_visit_status,
)
from app.services.planning_run_errors import PlanningRunError


_logger = logging.getLogger("uvicorn.error")
_DEBUG_PLANNING = os.getenv("PLANNING_DEBUG", "").lower() in ("true", "1", "yes")
_DEBUG_PLANNING_VISIT_IDS_RAW = os.getenv("PLANNING_DEBUG_VISIT_IDS", "")
try:
    _DEBUG_PLANNING_VISIT_IDS = {
        int(val.strip())
        for val in _DEBUG_PLANNING_VISIT_IDS_RAW.split(",")
        if val.strip()
    }
except ValueError:
    _DEBUG_PLANNING_VISIT_IDS = set()


DAYPART_TO_AVAIL_FIELD = {
    "Ochtend": "morning_days",
    "Dag": "daytime_days",
    "Avond": "nighttime_days",
}


def _parse_spare_capacity_by_daypart(raw: str) -> dict[str, int]:
    """Parse spare capacity per daypart from an env var string.

    The accepted format is a comma-separated list of `Daypart:count` pairs.
    Example: `Ochtend:1,Dag:2,Avond:2`.

    Args:
        raw: Raw env var value.

    Returns:
        Mapping of daypart label to non-negative spare capacity.
    """

    parsed: dict[str, int] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        key, _, val = part.partition(":")
        key = key.strip()
        val = val.strip()
        try:
            num = int(val)
        except ValueError:
            continue
        parsed[key] = max(0, num)
    return parsed


def _get_spare_capacity_by_daypart() -> dict[str, int]:
    """Return the configured spare capacity per daypart.

    Reads `SPARE_CAPACITY_BY_DAYPART` from the environment. For backwards
    compatibility, falls back to `SPARE_BY_DAYPART` when the new variable is
    unset.

    Returns:
        Mapping for the standard dayparts ("Ochtend", "Dag", "Avond"). Missing
        keys default to 0.
    """

    raw = os.getenv("SPARE_CAPACITY_BY_DAYPART")
    if raw is None:
        raw = os.getenv("SPARE_BY_DAYPART", "")

    spare = {
        "Ochtend": 0,
        "Dag": 0,
        "Avond": 0,
    }
    spare.update(_parse_spare_capacity_by_daypart(raw))
    return spare


def _end_of_work_week(week_monday: date) -> date:
    return week_monday + timedelta(days=4)


def _allowed_day_indices_for_visit(
    week_monday: date, visit: Visit, today: date | None = None
) -> list[int]:
    """Return 0-based indices (Mon=0..Fri=4) for days the visit can occur.

    The indices are the intersection of the visit's [from_date, to_date] window
    with the work week [week_monday, week_monday + 4]. If there is no
    intersection, the list is empty.
    """

    if today is None:
        today = date.today()

    week_friday = _end_of_work_week(week_monday)
    from_d = max(getattr(visit, "from_date", None) or date.min, week_monday)
    # Prevent assigning visits to days in the past during a mid-week run
    from_d = max(from_d, today)

    # Too late to plan Ochtend or Dag visits on the current day itself
    part = getattr(visit, "part_of_day", None)
    if from_d == today and part in ("Ochtend", "Dag"):
        from_d = today + timedelta(days=1)

    to_d = min(getattr(visit, "to_date", None) or date.max, week_friday)

    if from_d > to_d:
        return []

    indices: list[int] = []
    cur = from_d
    while cur <= to_d:
        idx = (cur - week_monday).days
        if 0 <= idx <= 4:
            indices.append(idx)
        cur += timedelta(days=1)
    return indices


def _first_function_name(v: Visit) -> str:
    try:
        return (v.functions[0].name or "").strip()
    except Exception:
        return ""


def _any_function_contains(v: Visit, needles: Iterable[str]) -> bool:
    names = [(f.name or "").lower() for f in (v.functions or [])]
    return any(any(needle.lower() in n for n in names) for needle in needles)


def _vleermuis_expertise_requirement(visit: Visit) -> str | None:
    """Return required expertise level for Vleermuis visits, if applicable.

    Args:
        visit: Visit candidate being evaluated.

    Returns:
        Normalized expertise level (lowercase) when the visit requires
        Vleermuis expertise, otherwise ``None``.
    """

    required = (getattr(visit, "expertise_level", None) or "").strip().lower()
    if not required:
        return None
    for sp in visit.species or []:
        fam_name = (
            getattr(getattr(sp, "family", None), "name", None)
            or getattr(sp, "name", None)
            or ""
        )
        if fam_name.strip().lower() == "vleermuis":
            return required
    return None


def _meets_vleermuis_expertise(user: User, visit: Visit) -> bool:
    """Return True if the user meets the Vleermuis expertise requirement.

    Args:
        user: Candidate researcher.
        visit: Visit being evaluated.

    Returns:
        ``True`` when no Vleermuis expertise level is required or the user's
        bat experience meets/exceeds the requirement.
    """

    required_expertise = _vleermuis_expertise_requirement(visit)
    if required_expertise is None:
        return True
    user_expertise = (getattr(user, "experience_bat", None) or "").strip().lower()
    expertise_rank = {"junior": 1, "medior": 2, "senior": 3}
    required_rank = expertise_rank.get(required_expertise, 0)
    user_rank = expertise_rank.get(user_expertise, 0)
    return required_rank == 0 or user_rank >= required_rank


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

    # Weight: tier0 (Season Plan) most significant.
    # tier0: Is this visit specifically provisionally planned for THIS week?
    # (Matches Architect's precise slot).
    # We need to access current week number. `week_monday` is passed.
    current_week = week_monday.isocalendar().week
    tier0 = bool(v.provisional_week == current_week)

    # Re-weight
    weight = (
        (int(tier0) << 8)
        | (int(tier1) << 7)
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
    from core.settings import get_settings

    if get_settings().feature_strict_availability:
        # Load strict capacities per user and sum them up
        user_daypart_caps = await _load_user_daypart_capacities_strict(db, week)

        total_morning = sum(
            caps.get("Ochtend", 0) for caps in user_daypart_caps.values()
        )
        total_daytime = sum(caps.get("Dag", 0) for caps in user_daypart_caps.values())
        total_night = sum(caps.get("Avond", 0) for caps in user_daypart_caps.values())
        total_flex = sum(caps.get("Flex", 0) for caps in user_daypart_caps.values())
    else:
        stmt = (
            select(AvailabilityWeek)
            .join(User, AvailabilityWeek.user_id == User.id)
            .where(
                and_(
                    AvailabilityWeek.week == week,
                    User.deleted_at.is_(None),
                )
            )
        )
        rows = (await db.execute(stmt)).scalars().all()

        total_morning = sum(r.morning_days or 0 for r in rows)
        total_daytime = sum(r.daytime_days or 0 for r in rows)
        total_night = sum(r.nighttime_days or 0 for r in rows)
        total_flex = sum(r.flex_days or 0 for r in rows)

    # Apply spare capacity caps (cannot go below zero)
    spare = _get_spare_capacity_by_daypart()
    total_morning = max(0, total_morning - spare["Ochtend"])
    total_daytime = max(0, total_daytime - spare["Dag"])
    total_night = max(0, total_night - spare["Avond"])

    return {
        "Ochtend": total_morning,
        "Dag": total_daytime,
        "Avond": total_night,
        "Flex": total_flex,
    }


async def _eligible_visits_for_week(db: AsyncSession, week_monday: date) -> list[Visit]:
    week_friday = _end_of_work_week(week_monday)

    from app.models.protocol_visit_window import ProtocolVisitWindow
    from app.models.protocol import Protocol
    from app.models.visit import visit_protocol_visit_windows

    async with db.begin_nested() if db.in_transaction() else db.begin() as _:
        # Sub-query for look-back logic (Protocol Frequency Control)
        # Find protocols that have 'locked' visits in the past, up to 8 weeks.
        # Then check if the gap between 'locked' visit and 'this week' is less than
        # the protocol's min_period.

        # 1. Determine Window [week - 8, week - 1]
        week_num = week_monday.isocalendar().week
        from core.settings import get_settings as _get_settings
        _pull_forward_weeks = _get_settings().week_planner_pull_forward_weeks
        # We look back up to 8 weeks (arbitrary safe upper bound for "weeks" or "months" periods)
        lookback_start = max(1, week_num - 8)
        lookback_end = max(0, week_num - 1)

        blocked_pairs: set[tuple[int, int]] = set()

        if lookback_end >= lookback_start:

            # Query visits that are planned in the lookback window AND have researchers
            # AND retrieve their associated protocol info (min_period value/unit)
            # AND the "end date" (or planned week) of the locked visit.

            # We need the Protocol object to get frequency settings.
            stmt_hist = (
                select(
                    Protocol.id,
                    Protocol.min_period_between_visits_value,
                    Protocol.min_period_between_visits_unit,
                    Visit.from_date,  # Use visit START date as reference for Optimistic Planning
                    Visit.planned_week,
                    Visit.cluster_id,
                )
                .join(
                    ProtocolVisitWindow, ProtocolVisitWindow.protocol_id == Protocol.id
                )
                .join(
                    visit_protocol_visit_windows,
                    visit_protocol_visit_windows.c.protocol_visit_window_id
                    == ProtocolVisitWindow.id,
                )
                .join(Visit, Visit.id == visit_protocol_visit_windows.c.visit_id)
                .where(
                    and_(
                        Visit.planned_week >= lookback_start,
                        Visit.planned_week <= lookback_end,
                        Visit.researchers.any(),  # Only locked/assigned visits count
                        # Ensure we are looking at roughly the same time period (year safety)
                        Visit.to_date >= (week_monday - timedelta(weeks=10)),
                    )
                )
            )
            rows_p = (await db.execute(stmt_hist)).unique().all()

            for (
                prot_id,
                min_val,
                min_unit,
                locked_visit_start,
                locked_week,
                locked_cluster_id,
            ) in rows_p:
                if not min_val:
                    continue

                # Calculate required gap
                # Units: 'days', 'weeks', 'months' (common convention, verify model if needed)
                # Use days for comparison.
                required_gap_days = 0
                if min_unit == "weeks":
                    required_gap_days = min_val * 7
                elif min_unit == "months":
                    required_gap_days = min_val * 30  # Approx
                else:  # days or None
                    required_gap_days = min_val

                # Gap = (Target Friday - Monday of locked_week).
                # Using planned_week Monday as reference gives the actual execution
                # date. The previous approach used from_date (window start), which
                # can be weeks earlier than when the visit was really planned,
                # causing the gap check to incorrectly pass.

                if locked_week:
                    try:
                        ref_year = (
                            locked_visit_start.year
                            if locked_visit_start
                            else week_monday.year
                        )
                        ref_date = date.fromisocalendar(ref_year, locked_week, 1)
                    except ValueError:
                        ref_date = locked_visit_start or week_monday
                else:
                    ref_date = locked_visit_start or week_monday

                # Target Friday
                target_friday = week_friday

                days_diff = (target_friday - ref_date).days

                if days_diff < required_gap_days:
                    # Block this protocol FOR THIS CLUSTER only
                    blocked_pairs.add((prot_id, locked_cluster_id))

        # Same-week block: visits that are planning_locked in the current week are
        # already committed and not in the candidate pool. Any sibling visit from
        # the same protocol+cluster in the same week would violate min_period
        # (intra-week gap is at most 4 days, so any min_period >= 5 days is
        # violated). Block those siblings unconditionally.
        stmt_locked_this_week = (
            select(Protocol.id, Visit.cluster_id)
            .join(
                ProtocolVisitWindow, ProtocolVisitWindow.protocol_id == Protocol.id
            )
            .join(
                visit_protocol_visit_windows,
                visit_protocol_visit_windows.c.protocol_visit_window_id
                == ProtocolVisitWindow.id,
            )
            .join(Visit, Visit.id == visit_protocol_visit_windows.c.visit_id)
            .where(
                and_(
                    Visit.planned_week == week_num,
                    Visit.planning_locked.is_(True),
                    Visit.deleted_at.is_(None),
                    Protocol.min_period_between_visits_value.isnot(None),
                )
            )
        )
        for prot_id, cluster_id in (
            await db.execute(stmt_locked_this_week)
        ).unique().all():
            blocked_pairs.add((prot_id, cluster_id))

    stmt = (
        select_active(Visit)
        .join(Cluster, Visit.cluster_id == Cluster.id)
        .join(Project, Cluster.project_id == Project.id)
        .where(
            and_(
                Visit.from_date <= week_friday,
                Visit.to_date >= week_monday,
                Visit.from_date <= week_friday,
                Visit.to_date >= week_monday,
                Project.quote.is_(False),
                # Season Planning Integration:
                # We ONLY consider visits that:
                # 1. Are Provisionally Planned for this week (or past weeks/overdue)
                # 2. OR Are Manually Locked (Priority)
                # 3. OR Are already Planned (Execution) but maybe we are re-optimizing?
                #
                # Wait! User said "Inbox" should also show "Possible" visits if searched.
                # But for the default "Auto-Select" or "Inbox List", we should focus on the Plan.
                # Actually, the function `_eligible_visits_for_week` is used by the Solver to PICK visits.
                # So we should RESTRICT it to what the Season Planner authorized + what is strictly necessary.
                # Logic:
                # - Match strictly feasible (Window intersection) -> Already handled by from_date/to_date above.
                # - Filter by Provisional Week logic:
                #   - If provisional_week IS SET: Allow if provisional_week <= current_week?
                #   - What if it's set to NEXT week? Then we should HIDE it (it's for future).
                #   - What if it's NOT set (Unplannable)? We generally ignore it unless forced?
                #     (User said unplannable go to capacity page).
                # Current Logic Implementation:
                # We relax the strict filter to allow the "Search" case, OR we stick to the Plan.
                # Given "Candidate / Pull List" requirement, we probably shouldn't HARD filter in the DB query
                # if this function powers the "Inbox" list too.
                # BUT this function is named `_eligible_visits_for_week` and powers the CP-SAT Weekly Solver.
                # The Weekly Solver should ONLY optimize what is on the menu.
                # So:
                or_(
                    # A. Authorized by Season Planner (Current or Past Overdue),
                    # plus up to _pull_forward_weeks future weeks so the weekly planner
                    # can pull upcoming visits forward when capacity is still available.
                    Visit.provisional_week <= week_num + _pull_forward_weeks,
                    # B. Safety: Allow if provisional_week IS NULL (new visits not yet simulated)
                    Visit.provisional_week.is_(None),
                ),
                # Exclude visits that are already planned with assigned researchers,
                # unless researchers_locked (client-specified researchers that must be
                # re-confirmed by the solver each week).
                or_(
                    Visit.planned_week.is_(None),
                    ~Visit.researchers.any(),
                    Visit.researchers_locked.is_(True),
                ),
                # Exclude custom visits (manual planning only)
                Visit.custom_function_name.is_(None),
                Visit.custom_species_name.is_(None),
                Visit.custom_species_name.is_(None),
            )
        )
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.protocol_visit_windows).selectinload(ProtocolVisitWindow.protocol),
        )
    )

    candidates = (await db.execute(stmt)).scalars().unique().all()

    if _DEBUG_PLANNING and _DEBUG_PLANNING_VISIT_IDS:
        debug_stmt = (
            select(Visit)
            .where(Visit.id.in_(_DEBUG_PLANNING_VISIT_IDS))
            .options(selectinload(Visit.cluster).selectinload(Cluster.project))
        )
        debug_visits = (await db.execute(debug_stmt)).scalars().unique().all()
        candidate_ids = {v.id for v in candidates}
        for v in debug_visits:
            vid = getattr(v, "id", None)
            if vid in candidate_ids:
                _logger.debug(
                    "planning_debug visit_id=%s eligible_stage=pre_blocked",
                    vid,
                )
                continue

            reasons: list[str] = []
            project = getattr(v.cluster, "project", None) if v.cluster else None
            if project and getattr(project, "quote", False):
                reasons.append("project_quote")
            if getattr(v, "custom_function_name", None) or getattr(
                v, "custom_species_name", None
            ):
                reasons.append("custom_visit")

            date_ok = bool(
                (getattr(v, "from_date", None) and getattr(v, "to_date", None))
                and v.from_date <= week_friday
                and v.to_date >= week_monday
            )
            if not date_ok:
                reasons.append("outside_week_window")

            week_num = week_monday.isocalendar().week
            prov_week = getattr(v, "provisional_week", None)
            planned_week = getattr(v, "planned_week", None)
            provisional_ok = (
                (prov_week is not None and prov_week <= week_num)
                or planned_week is not None
                or prov_week is None
            )
            if not provisional_ok:
                reasons.append("provisional_week_future")

            _logger.debug(
                "planning_debug visit_id=%s excluded_stage=base_filters reasons=%s",
                vid,
                reasons,
            )

    # Filter out candidates belonging to blocked (protocol, cluster) pairs
    if blocked_pairs:
        pre_dedup = []
        for v in candidates:
            v_pids = {pvw.protocol_id for pvw in (v.protocol_visit_windows or [])}
            is_blocked = any(
                (pid, v.cluster_id) in blocked_pairs for pid in v_pids
            )
            if is_blocked:
                if _DEBUG_PLANNING and v.id in _DEBUG_PLANNING_VISIT_IDS:
                    _logger.debug(
                        "planning_debug visit_id=%s excluded_stage=blocked_pairs",
                        v.id,
                    )
            else:
                pre_dedup.append(v)
    else:
        pre_dedup = list(candidates)

    # Intra-week protocol frequency deduplication.
    # A protocol with min_period > 0 may appear at most once per (protocol, cluster)
    # per planning week. When two visits of the same protocol+cluster are both
    # eligible (their windows overlap the current week), only the one with the
    # earliest from_date passes through. The later visit will be picked up in a
    # subsequent planning run once the gap requirement is satisfied.
    #
    # This guards against the case where the backwards lookback cannot help:
    # neither visit is locked yet, so there is nothing in the history to block on.
    proto_cluster_winner: dict[tuple[int, int], int] = {}  # key -> winning visit.id

    for v in pre_dedup:
        v_from = v.from_date or date.min
        for pvw in (v.protocol_visit_windows or []):
            prot = getattr(pvw, "protocol", None)
            if not prot or not prot.min_period_between_visits_value:
                continue
            key = (prot.id, v.cluster_id)
            if key not in proto_cluster_winner:
                proto_cluster_winner[key] = v.id
            else:
                winner_id = proto_cluster_winner[key]
                winner = next((x for x in pre_dedup if x.id == winner_id), None)
                winner_from = (winner.from_date if winner else None) or date.min
                if v_from < winner_from:
                    proto_cluster_winner[key] = v.id

    filtered = []
    for v in pre_dedup:
        is_dedup_blocked = False
        for pvw in (v.protocol_visit_windows or []):
            prot = getattr(pvw, "protocol", None)
            if not prot or not prot.min_period_between_visits_value:
                continue
            key = (prot.id, v.cluster_id)
            if proto_cluster_winner.get(key) != v.id:
                is_dedup_blocked = True
                break
        if is_dedup_blocked:
            if _DEBUG_PLANNING and v.id in _DEBUG_PLANNING_VISIT_IDS:
                _logger.debug(
                    "planning_debug visit_id=%s excluded_stage=intra_week_protocol_dedup",
                    v.id,
                )
        else:
            filtered.append(v)

    return filtered


def _is_huismus_visit(v: Visit) -> bool:
    """Return True if the visit has at least one Huismus-family species."""
    for sp in v.species or []:
        fam_name = (
            getattr(getattr(sp, "family", None), "name", None) or ""
        ).strip().lower()
        if fam_name == "huismus":
            return True
    return False


_HUISMUS_NEST_FUNCTIONS = {"Nest", "Nest en FL"}


def _is_huismus_nest_visit(v: Visit) -> bool:
    """Return True if the visit has Huismus-family species AND function is 'Nest' or 'Nest en FL'.

    Used by the Huismus-pairing feature to restrict pairing to the relevant visit types.
    """
    fn = _first_function_name(v)
    if fn not in _HUISMUS_NEST_FUNCTIONS:
        return False
    return _is_huismus_visit(v)


async def _load_huismus_pairing_candidates(
    db: AsyncSession, week_monday: date, week_num: int
) -> list[Visit]:
    """Load Huismus visits eligible for pairing but outside the regular solver pool.

    These are open Huismus visits whose date window overlaps with the current week
    but whose provisional_week is in the future (> week_num). They have no assigned
    researchers. The solver may pull them into the current week exclusively as the
    second visit of a Huismus pair.
    """
    week_friday = _end_of_work_week(week_monday)

    stmt = (
        select_active(Visit)
        .join(Cluster, Visit.cluster_id == Cluster.id)
        .join(Project, Cluster.project_id == Project.id)
        .where(
            and_(
                Visit.from_date <= week_friday,
                Visit.to_date >= week_monday,
                Project.quote.is_(False),
                # Only visits provisionally planned for a FUTURE week
                Visit.provisional_week > week_num,
                # Not yet assigned
                or_(Visit.planned_week.is_(None), ~Visit.researchers.any()),
                # Not custom visits
                Visit.custom_function_name.is_(None),
                Visit.custom_species_name.is_(None),
                # Only Huismus family
                Visit.species.any(
                    Species.family.has(Family.name.ilike("huismus"))
                ),
                # Only 'Nest' or 'Nest en FL' function visits
                Visit.functions.any(Function.name.in_(["Nest", "Nest en FL"])),
            )
        )
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.protocol_visit_windows),
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
        # Butterfly species (Iepenpage, Grote vos) are handled via a shared 'vlinder' flag.
        # We keep keys for both species names and the generic family label in case future
        # data uses one or the other.
        "vlinder": "vlinder",
        "grote vos": "vlinder",
        "iepenpage": "vlinder",
        "teunisbloempijlstaart": "teunisbloempijlstaart",
        "huismus": "zangvogel",
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
        elif fam_name == "huismus":
            required_attr = "smp_huismus"
        uid = getattr(user, "id", None)
        if required_attr is not None:
            smp_ok = bool(getattr(user, required_attr, False))
            if not smp_ok:
                if _DEBUG_PLANNING:
                    _logger.debug(
                        "planning: user_id=%s unqualified_for_visit_id=%s reason=smp_flag_missing attr=%s",
                        uid,
                        getattr(visit, "id", None),
                        required_attr,
                    )
                return False
        else:
            _logger.warning(
                "Unknown SMP function %s for species %s with family %s. Could not assign visit.",
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
                if _DEBUG_PLANNING:
                    _logger.debug(
                        "planning: user_id=%s unqualified_for_visit_id=%s reason=family_flag_missing family_key=%s attr=%s",
                        getattr(user, "id", None),
                        getattr(visit, "id", None),
                        key,
                        attr,
                    )
                return False
        # Direct species name enforcement as an extra safety net
        for key, attr in fam_to_user_attr.items():
            if key in species_names_lower and not bool(getattr(user, attr, False)):
                if _DEBUG_PLANNING:
                    _logger.debug(
                        "planning: user_id=%s unqualified_for_visit_id=%s reason=species_flag_missing species_key=%s attr=%s",
                        getattr(user, "id", None),
                        getattr(visit, "id", None),
                        key,
                        attr,
                    )
                return False

    # Vleermuis expertise rule
    if not _meets_vleermuis_expertise(user, visit):
        if _DEBUG_PLANNING:
            _logger.debug(
                "planning: user_id=%s unqualified_for_visit_id=%s reason=expertise_level_missing required=%s actual=%s",
                getattr(user, "id", None),
                getattr(visit, "id", None),
                _vleermuis_expertise_requirement(visit),
                (getattr(user, "experience_bat", None) or "").strip().lower() or None,
            )
        return False

    # VRFG function rule
    if _any_function_contains(visit, ("Vliegroute", "Foerageergebied")):
        if not bool(getattr(user, "vrfg", False)):
            if _DEBUG_PLANNING:
                _logger.debug(
                    "planning: user_id=%s unqualified_for_visit_id=%s reason=vrfg_missing",
                    getattr(user, "id", None),
                    getattr(visit, "id", None),
                )
            return False

    # Visit flags that must exist on user when required. "sleutel" is handled
    # separately during assignment based on contract type.
    for flag in ("hub", "fiets", "wbc", "dvp", "vog"):
        if bool(getattr(visit, flag, False)) and not bool(getattr(user, flag, False)):
            if _DEBUG_PLANNING:
                _logger.debug(
                    "planning: user_id=%s unqualified_for_visit_id=%s reason=visit_flag_missing flag=%s",
                    getattr(user, "id", None),
                    getattr(visit, "id", None),
                    flag,
                )
            return False

    return True


async def _load_all_users(db: AsyncSession) -> list[User]:
    """Load all users once. Extracted for easier monkeypatching in tests."""
    return (await db.execute(select(User).order_by(User.id))).scalars().all()


async def _load_user_capacities(db: AsyncSession, week: int) -> dict[int, int]:
    """Return per-user total capacity for the ISO week (sum of all dayparts + flex)."""
    from core.settings import get_settings

    if get_settings().feature_strict_availability:
        return await _load_user_capacities_strict(db, week)
    try:
        stmt = (
            select(AvailabilityWeek)
            .join(User, AvailabilityWeek.user_id == User.id)
            .where(
                and_(
                    AvailabilityWeek.week == week,
                    User.deleted_at.is_(None),
                )
            )
        )
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


async def _load_user_daypart_capacities(
    db: AsyncSession, week: int
) -> dict[int, dict[str, int]]:
    """Return per-user remaining capacity per daypart for the ISO week.

    The mapping keys are user ids; values are dictionaries keyed by the human
    readable part-of-day labels used in DAYPART_TO_AVAIL_FIELD ("Ochtend",
    "Dag", "Avond") plus "Flex".
    """
    from core.settings import get_settings

    if get_settings().feature_strict_availability:
        return await _load_user_daypart_capacities_strict(db, week)
    try:
        stmt = (
            select(AvailabilityWeek)
            .join(User, AvailabilityWeek.user_id == User.id)
            .where(
                and_(
                    AvailabilityWeek.week == week,
                    User.deleted_at.is_(None),
                )
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        # In tests a fake DB may not support this; treat as unlimited capacity.
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
        except Exception:
            # Skip malformed rows from fakes
            continue
    return per_user


def _build_initial_day_schedule(
    per_user_caps: dict[int, dict[str, int]],
) -> dict[int, list[bool]]:
    """Construct an in-memory per-day schedule for the work week.

    The per-day structure only enforces that we do not assign more than one
    visit per (user, weekday) within a single planning run. Weekly numeric
    capacities from ``AvailabilityWeek`` are still enforced by the existing
    per-user capacity helpers and are **not** encoded as specific weekdays
    here.
    """

    schedule: dict[int, list[bool]] = {}
    for uid in per_user_caps.keys():
        schedule[uid] = [True] * 5
    return schedule


async def _apply_existing_assignments_to_capacities(
    db: AsyncSession,
    week: int,
    per_user_capacity: dict[int, int],
    per_user_daypart_caps: dict[int, dict[str, int]],
) -> None:
    """Subtract capacity for visits already planned in the given ISO week.

    This accounts for visits that already have researchers assigned and a
    matching ``planned_week`` before a new planning run starts. Each such
    assignment consumes one unit of the user's total weekly capacity and one
    unit of the corresponding part-of-day capacity (falling back to Flex using
    the same rules as the planner).

    To avoid interfering with tests that use fake DB objects, this helper only
    runs when ``db`` is an actual AsyncSession instance.
    """

    # In unit tests a lightweight fake DB object is often used; skip in that case.
    if not isinstance(db, AsyncSession):  # type: ignore[arg-type]
        return

    try:
        stmt = (
            select_active(Visit)
            .where(Visit.planned_week == week)
            .options(selectinload(Visit.researchers))
        )
        planned_visits: list[Visit] = (await db.execute(stmt)).scalars().unique().all()
    except Exception:  # pragma: no cover - defensive for unexpected DB issues
        return

    for v in planned_visits:
        part = (getattr(v, "part_of_day", "") or "").strip()
        if part not in DAYPART_TO_AVAIL_FIELD:
            continue

        for u in getattr(v, "researchers", []) or []:
            uid = getattr(u, "id", None)
            if uid is None:
                continue

            # Decrease total weekly capacity for fairness ratios.
            if uid in per_user_capacity:
                per_user_capacity[uid] = max(0, per_user_capacity.get(uid, 0) - 1)

            # Decrease per-daypart capacity using the same rules as regular
            # assignment (dedicated part first, then Flex).
            _consume_user_capacity(per_user_daypart_caps, uid, part)


def _user_has_capacity_for_visit(
    per_user_caps: dict[int, dict[str, int]], uid: int, part: str
) -> bool:
    """Return True if the user has at least one slot for the visit's part.

    If no per-user capacity info is available for this user, we treat this as
    unlimited capacity to preserve behaviour in tests that use fake DBs
    without availability rows.
    """

    # If we have no per-user capacity information at all (e.g. in tests with
    # fake DBs that do not provide AvailabilityWeek rows), treat this as
    # unlimited capacity to preserve historical behaviour.
    if not per_user_caps:
        return True

    # When some availability data exists for the week, the absence of a row
    # for a specific user means that user has no capacity in this week.
    caps = per_user_caps.get(uid)
    if caps is None:
        _logger.debug(
            "planning: user_id=%s no_capacity_for_part=%s reason=no_availability_row",
            uid,
            part,
        )
        return False

    have = caps.get(part, 0)
    if have > 0:
        return True
    flex = caps.get("Flex", 0)
    if flex > 0:
        return True

    _logger.debug(
        "planning: user_id=%s no_capacity_for_part=%s reason=insufficient_caps caps=%s",
        uid,
        part,
        caps,
    )
    return False


def _compute_strict_daypart_caps(
    patterns: list,
    unavailabilities: list,
    week: int,
    year: int,
    org_unavailabilities: list | None = None,
) -> tuple[int, int, int]:
    """Compute per-daypart capacity from AvailabilityPattern records for a given week.

    Iterates each day of the week, finds the active pattern (if any), and counts
    how many days each daypart slot appears in the schedule. Applies per-daypart caps
    and skips periods marked by UserUnavailability or OrganizationUnavailability.

    Returns (morning_days, daytime_days, nighttime_days, specific_days).
    """
    if org_unavailabilities is None:
        org_unavailabilities = []

    try:
        w_start = date.fromisocalendar(year, week, 1)
    except ValueError:
        return 0, 0, 0, {"Ochtend": [], "Dag": [], "Avond": []}

    day_names = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    morning_days = 0
    daytime_days = 0
    nighttime_days = 0
    max_mornings: int = 2
    max_evenings: int = 5

    specific_days = {"Ochtend": [], "Dag": [], "Avond": []}

    for i in range(7):
        day_date = w_start + timedelta(days=i)

        active_unavail = next(
            (u for u in unavailabilities if u.start_date <= day_date <= u.end_date),
            None,
        )
        active_org_unavail = next(
            (u for u in org_unavailabilities if u.start_date <= day_date <= u.end_date),
            None,
        )

        active = next(
            (p for p in patterns if p.start_date <= day_date <= p.end_date),
            None,
        )
        if active is None:
            continue

        if active.max_mornings_per_week is not None:
            max_mornings = active.max_mornings_per_week
        if active.max_evenings_per_week is not None:
            max_evenings = active.max_evenings_per_week

        slots = active.schedule.get(day_names[i], [])

        morning_blocked = (
            active_unavail and getattr(active_unavail, "morning", True)
        ) or (active_org_unavail and getattr(active_org_unavail, "morning", True))
        daytime_blocked = (
            active_unavail and getattr(active_unavail, "daytime", True)
        ) or (active_org_unavail and getattr(active_org_unavail, "daytime", True))
        nighttime_blocked = (
            active_unavail and getattr(active_unavail, "nighttime", True)
        ) or (active_org_unavail and getattr(active_org_unavail, "nighttime", True))

        if "morning" in slots and not morning_blocked:
            morning_days += 1
            if i < 5:
                specific_days["Ochtend"].append(i)
        if "daytime" in slots and not daytime_blocked:
            daytime_days += 1
            if i < 5:
                specific_days["Dag"].append(i)
        if "nighttime" in slots and not nighttime_blocked:
            nighttime_days += 1
            if i < 5:
                specific_days["Avond"].append(i)

    return (
        min(morning_days, max_mornings),
        min(daytime_days, 5),
        min(nighttime_days, max_evenings),
        specific_days,
    )


async def _load_user_capacities_strict(db: AsyncSession, week: int) -> dict[int, int]:
    """Load per-user total capacity from AvailabilityPattern (strict availability mode)."""
    from app.models.availability_pattern import AvailabilityPattern

    year = date.today().year
    try:
        w_start = date.fromisocalendar(year, week, 1)
    except ValueError:
        return {}
    w_end = w_start + timedelta(days=6)

    try:
        stmt = (
            select(AvailabilityPattern)
            .join(User, AvailabilityPattern.user_id == User.id)
            .where(
                and_(
                    User.deleted_at.is_(None),
                    AvailabilityPattern.deleted_at.is_(None),
                    AvailabilityPattern.start_date <= w_end,
                    AvailabilityPattern.end_date >= w_start,
                )
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        return {}

    patterns_by_user: dict[int, list] = {}
    for p in rows:
        patterns_by_user.setdefault(p.user_id, []).append(p)

    try:
        from app.models.user_unavailability import UserUnavailability

        stmt_u = (
            select(UserUnavailability)
            .join(User, UserUnavailability.user_id == User.id)
            .where(
                and_(
                    User.deleted_at.is_(None),
                    UserUnavailability.start_date <= w_end,
                    UserUnavailability.end_date >= w_start,
                )
            )
        )
        rows_u = (await db.execute(stmt_u)).scalars().all()
    except Exception:
        rows_u = []

    unavail_by_user: dict[int, list] = {}
    for u in rows_u:
        unavail_by_user.setdefault(u.user_id, []).append(u)

    try:
        from app.models.organization_unavailability import OrganizationUnavailability

        stmt_org = select(OrganizationUnavailability).where(
            and_(
                OrganizationUnavailability.deleted_at.is_(None),
                OrganizationUnavailability.start_date <= w_end,
                OrganizationUnavailability.end_date >= w_start,
            )
        )
        org_unavail_rows = (await db.execute(stmt_org)).scalars().all()
    except Exception:
        org_unavail_rows = []

    caps: dict[int, int] = {}
    for uid, user_patterns in patterns_by_user.items():
        m, d, n, _ = _compute_strict_daypart_caps(
            user_patterns,
            unavail_by_user.get(uid, []),
            week,
            year,
            list(org_unavail_rows),
        )
        total = m + d + n
        caps[uid] = total

    return caps


async def _load_user_daypart_capacities_strict(
    db: AsyncSession, week: int
) -> dict[int, dict[str, int]]:
    """Load per-user daypart capacity from AvailabilityPattern (strict availability mode)."""
    from app.models.availability_pattern import AvailabilityPattern

    year = date.today().year
    try:
        w_start = date.fromisocalendar(year, week, 1)
    except ValueError:
        return {}
    w_end = w_start + timedelta(days=6)

    try:
        stmt = (
            select(AvailabilityPattern)
            .join(User, AvailabilityPattern.user_id == User.id)
            .where(
                and_(
                    User.deleted_at.is_(None),
                    AvailabilityPattern.deleted_at.is_(None),
                    AvailabilityPattern.start_date <= w_end,
                    AvailabilityPattern.end_date >= w_start,
                )
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        return {}

    patterns_by_user: dict[int, list] = {}
    for p in rows:
        patterns_by_user.setdefault(p.user_id, []).append(p)

    try:
        from app.models.user_unavailability import UserUnavailability

        stmt_u = (
            select(UserUnavailability)
            .join(User, UserUnavailability.user_id == User.id)
            .where(
                and_(
                    User.deleted_at.is_(None),
                    UserUnavailability.start_date <= w_end,
                    UserUnavailability.end_date >= w_start,
                )
            )
        )
        rows_u = (await db.execute(stmt_u)).scalars().all()
    except Exception:
        rows_u = []

    unavail_by_user: dict[int, list] = {}
    for u in rows_u:
        unavail_by_user.setdefault(u.user_id, []).append(u)

    try:
        from app.models.organization_unavailability import OrganizationUnavailability

        stmt_org = select(OrganizationUnavailability).where(
            and_(
                OrganizationUnavailability.deleted_at.is_(None),
                OrganizationUnavailability.start_date <= w_end,
                OrganizationUnavailability.end_date >= w_start,
            )
        )
        org_unavail_rows = (await db.execute(stmt_org)).scalars().all()
    except Exception:
        org_unavail_rows = []

    per_user: dict[int, dict[str, int | dict[str, list[int]]]] = {}
    for uid, user_patterns in patterns_by_user.items():
        m, d, n, specific_days = _compute_strict_daypart_caps(
            user_patterns,
            unavail_by_user.get(uid, []),
            week,
            year,
            list(org_unavail_rows),
        )
        per_user[uid] = {
            "Ochtend": m,
            "Dag": d,
            "Avond": n,
            "Flex": 0,
            "days": specific_days,
        }

    return per_user


def _consume_user_capacity(
    per_user_caps: dict[int, dict[str, int]], uid: int, part: str
) -> bool:
    """Consume one capacity unit for the given user and part.

    Prefers dedicated part capacity but will fall back to Flex if needed.
    Returns False if neither dedicated nor flex capacity is available. When no
    per-user capacity information is present for the user, this is treated as
    a no-op with unlimited capacity and returns True.
    """

    caps = per_user_caps.get(uid)
    if caps is None:
        return True

    have = caps.get(part, 0)
    if have > 0:
        caps[part] = have - 1
        return True

    flex = caps.get("Flex", 0)
    if flex > 0:
        caps["Flex"] = flex - 1
        return True

    return False


def _user_is_intern(user: User) -> bool:
    """Return True if the user's contract type is INTERN.

    In production this compares against the User.ContractType enum. In tests we
    also support a plain string value "Intern" for convenience when using
    simple namespaces.
    """

    contract = getattr(user, "contract", None)
    if contract is None:
        return False
    # Enum instance from the SQLAlchemy model
    if isinstance(contract, User.ContractType):
        return contract == User.ContractType.INTERN
    # Fallback for tests using plain strings
    return str(contract) == "Intern"


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


async def _select_visits_for_week_core(
    db: AsyncSession | None, week_monday: date
) -> tuple[list[Visit], list[Visit], dict]:
    """Core selection logic shared between planning and simulations.

    This helper loads weekly capacity, fetches eligible visits, applies the
    configured priority ordering and consumes capacity per daypart using the
    same rules as the planner. It returns the selected and skipped visits
    together with the remaining capacity buckets.
    """

    week = week_monday.isocalendar().week
    caps = await _load_week_capacity(db, week)  # type: ignore[arg-type]

    visits = await _eligible_visits_for_week(db, week_monday)  # type: ignore[arg-type]

    # Normalize planned_week vs researchers invariant before status filtering.
    # [REMOVED] destructive normalization that modified objects in-place.
    # Logic should be robust enough to handle partial states or normalization
    # should happen explicitly during save, not read/simulation.

    # Filter to visits that are currently OPEN according to the centralized
    # status service. Use ``week_monday`` as the reference "today" so that
    # simulations and tests for historical weeks remain deterministic.
    if db is not None:
        filtered: list[Visit] = []
        for v in visits:
            try:
                status = await resolve_visit_status(db, v, today=week_monday)
            except Exception:  # pragma: no cover - defensive only
                status = derive_visit_status(v, None, today=week_monday)
            if status == VisitStatusCode.OPEN:
                filtered.append(v)
        visits = filtered
    else:
        visits = [
            v
            for v in visits
            if derive_visit_status(v, None, today=week_monday) == VisitStatusCode.OPEN
        ]

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

    return selected, skipped, caps


def _apply_gz_remark(visit: Visit) -> None:
    """Post-processing: add a personalized GZ-gedeelte remark for combined vleermuis/GZ zwaluw visits.

    Randomly picks one researcher for the GZ-gedeelte so that it's not always
    the same person. Removes any previous version of this remark before appending
    the updated one, so re-running the planner won't duplicate it.
    Only applies when more than one researcher is assigned.
    """
    has_vleermuis = any(
        getattr(getattr(sp, "family", None), "name", "") == "Vleermuis"
        for sp in (visit.species or [])
    )
    has_gz_zwaluw = any(
        getattr(getattr(sp, "family", None), "name", "") == "Zwaluw"
        and getattr(sp, "abbreviation", "") == "GZ"
        for sp in (visit.species or [])
    )
    if not (has_vleermuis and has_gz_zwaluw):
        return

    researchers = list(visit.researchers or [])
    if len(researchers) <= 1:
        return

    def _first_name(user: User) -> str:
        return ((getattr(user, "full_name", None) or "").split() + ["?"])[0]

    gz_researcher = random.choice(researchers)
    others = [u for u in researchers if u is not gz_researcher]

    gz_name = _first_name(gz_researcher)
    other_names = [_first_name(u) for u in others]
    others_str = " en ".join(other_names)
    verb = "begint" if len(other_names) == 1 else "beginnen"
    new_remark = f"{gz_name} voor GZ-gedeelte. {others_str} {verb} bij zonsondergang."

    # Remove any existing GZ-gedeelte remark (old static or previous dynamic run)
    existing = visit.remarks_field or ""
    cleaned = re.sub(r"[^\n]*voor GZ-gedeelte[^\n]*\n?", "", existing).strip()
    visit.remarks_field = (
        (cleaned + "\n" + new_remark).strip() if cleaned else new_remark
    )


async def select_visits_for_week(
    db: AsyncSession,
    week_monday: date,
    timeout_seconds: float | None = None,
    include_travel_time: bool = True,
    today: date | None = None,
) -> dict:
    """Run CP-SAT solver for a given week.

    Loads all relevant data (visits, users, capacities) and invokes the
    solver to produce a recommended schedule. The result is returned as a
    dictionary with detailed assignment info.
    """
    from app.services.visit_selection_ortools import select_visits_cp_sat

    # Legacy support for tests that pass db=None to verify global constraints only
    if db is None:
        selected, skipped, caps = await _select_visits_for_week_core(db, week_monday)
        return {
            "selected_visit_ids": [v.id for v in selected],
            "skipped_visit_ids": [v.id for v in skipped],
            "capacity_remaining": caps,
        }

    try:
        result = await select_visits_cp_sat(
            db,
            week_monday,
            timeout_seconds=timeout_seconds,
            include_travel_time=include_travel_time,
            today=today,
        )
    except PlanningRunError:
        if db:
            await db.rollback()
        raise

    effective_selected = result.selected
    effective_skipped = result.skipped
    day_assignments = result.day_assignments or {}
    week = week_monday.isocalendar().week

    # Persist planning diagnostics (why each visit was skipped) to ActivityLog.
    # Delete previous diagnostics for this week before writing fresh ones.
    if db and isinstance(db, AsyncSession):
        await db.execute(
            delete(ActivityLog).where(
                and_(
                    ActivityLog.action == "planning_week_skipped",
                    ActivityLog.target_id == week,
                )
            )
        )
        batch = str(uuid4())

        # Solver-level diagnostics: visits the solver received but didn't schedule.
        for d in result.diagnostics:
            db.add(
                ActivityLog(
                    action="planning_week_skipped",
                    target_type="planning_week",
                    target_id=week,
                    details={
                        "visit_id": d.visit_id,
                        "week": week,
                        "reason_code": d.reason_code,
                        "reason_nl": d.reason_nl,
                    },
                    batch_id=batch,
                )
            )

        # Post-hoc: detect Voorlopig visits that were invisible to the solver
        # (filtered out before the solver ran, e.g. date-window mismatch or protocol
        # frequency block). Load all Voorlopig visits for this week and compare.
        week_friday = week_monday + timedelta(days=4)
        solver_seen_ids = {v.id for v in result.selected} | {
            v.id for v in result.skipped
        }

        voorlopig_stmt = select_active(Visit).where(
            and_(
                Visit.provisional_week == week,
                or_(Visit.planned_week.is_(None), ~Visit.researchers.any()),
            )
        )
        voorlopig_visits = (await db.execute(voorlopig_stmt)).scalars().unique().all()

        for v in voorlopig_visits:
            if v.id in solver_seen_ids:
                continue
            from_d = getattr(v, "from_date", None)
            to_d = getattr(v, "to_date", None)
            window_overlaps = (
                from_d is not None
                and to_d is not None
                and from_d <= week_friday
                and to_d >= week_monday
            )
            if not window_overlaps:
                reason_code = "venster_buiten_week"
                reason_nl = (
                    f"Het uitvoeringsvenster ({from_d} t/m {to_d}) overlapt niet "
                    f"met werkweek {week} ({week_monday} t/m {week_friday})."
                )
            else:
                reason_code = "protocol_frequentie"
                reason_nl = (
                    "Bezoek tijdelijk geblokkeerd: een eerder bezoek van hetzelfde "
                    "protocol staat al ingepland en de minimale tussentijd is nog "
                    "niet verstreken."
                )
            db.add(
                ActivityLog(
                    action="planning_week_skipped",
                    target_type="planning_week",
                    target_id=week,
                    details={
                        "visit_id": v.id,
                        "week": week,
                        "reason_code": reason_code,
                        "reason_nl": reason_nl,
                    },
                    batch_id=batch,
                )
            )

    # Post-processing: add personalized GZ-gedeelte remark for combined visits.
    for v in effective_selected:
        _apply_gz_remark(v)

    if db:
        await db.commit()

    # Re-calculate remaining global capacity for reporting purposes (UI)
    caps = await _load_week_capacity(db, week)

    for v in effective_selected:
        part = (v.part_of_day or "").strip()
        if part in DAYPART_TO_AVAIL_FIELD:
            required = max(1, v.required_researchers or 1)
            # Simulate consumption for logging purposes
            _consume_capacity(caps, part, required)

    # Log output
    if effective_selected:
        _logger.info("Selected visits for week starting %s:", week_monday.isoformat())
        for v in effective_selected:
            _logger.info(_format_visit_line(v))
    else:
        _logger.info("No visits selected for week starting %s", week_monday.isoformat())

    return {
        "selected_visit_ids": [v.id for v in effective_selected],
        "skipped_visit_ids": [v.id for v in effective_skipped],
        "capacity_remaining": caps,
        "day_assignments": day_assignments,
        "planning_warning": result.planning_warning,
    }

from __future__ import annotations

import logging
import re
from datetime import date
from typing import NamedTuple

from ortools.sat.python import cp_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.user import User
from app.services.planning_run_errors import PlanningRunError
from core.settings import get_settings

_logger = logging.getLogger("uvicorn.error")


def _full_addr_for_travel_time(cluster) -> str | None:
    """Return the canonical address string used for travel-time lookups.

    For coordinate-based addresses (decimal or DMS), the address is returned
    as-is.  For street addresses the location is appended for unambiguous
    geocoding: cluster.location takes precedence over project.location (the
    same precedence used elsewhere in the codebase).

    Address "-" (a common placeholder) is treated as absent.  If no usable
    street address is present, the location alone is returned so that
    city-level travel times can still be estimated.
    """
    raw = (getattr(cluster, "address", None) or "").strip()
    addr = raw if raw and raw != "-" else None

    is_coords = bool(
        addr and (
            re.match(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$", addr)
            or re.match(r"^\d+°", addr)
        )
    )
    if is_coords:
        return addr

    loc = (
        getattr(cluster, "location", None)
        or getattr(getattr(cluster, "project", None), "location", None)
    )

    if addr and loc:
        return f"{addr}, {loc}"
    if addr:
        return addr
    return loc or None


class WeeklyPlanningDiagnostic(NamedTuple):
    """Diagnostic entry for a visit skipped during weekly planning."""

    visit_id: int
    reason_code: str  # e.g. "geen_dagdeel", "geen_gekwalificeerde_onderzoekers"
    reason_nl: str  # Human-readable Dutch explanation


class VisitSelectionResult(NamedTuple):
    selected: list[Visit]
    skipped: list[Visit]
    remaining_caps: dict[str, int]  # Global daypart caps (approximate)
    day_assignments: dict[int, date] | None = None  # visit_id -> date
    diagnostics: list[WeeklyPlanningDiagnostic] = []  # Per-visit skip reasons
    planning_warning: str | None = None  # Set when solution is WEAK but still usable


def _generate_greedy_planning_solution(
    visits: list[Visit],
    users: list[User],
    user_caps: dict[int, int],
    user_daypart_caps: dict[int, dict[str, int]],
    week_monday: date,
    today: date | None = None,
) -> tuple[set[int], dict[int, int], dict[int, list[int]]]:
    """
    Generate a Greedy First-Fit solution for planning.

    Returns:
    - scheduled_indices: set of visit indices (in local 'visits' list)
    - visit_days: dict {v_idx: day_idx (0-4)}
    - visit_assignments: dict {v_idx: [u_idx (in local 'users' list), ...]}
    """
    from app.services.visit_planning_selection import (
        _allowed_day_indices_for_visit,
        _qualifies_user_for_visit,
    )

    # Mutable State
    # We clone caps roughly to track usage
    # user_rem_weekly: {uid: int}
    user_rem_weekly = {uid: cap for uid, cap in user_caps.items()}

    # user_rem_daypart: {uid: {part: int, 'Flex': int}}
    # Deep copy needed
    user_rem_daypart = {}
    for uid, caps in user_daypart_caps.items():
        user_rem_daypart[uid] = caps.copy()

    # user_busy: {uid: {day_idx}} - prevent multi-booking per day
    user_busy: dict[int, set[int]] = {}
    for u in users:
        user_busy[getattr(u, "id", 0)] = set()

    scheduled_indices = set()
    visit_days = {}
    visit_assigns = {}

    # Iterate visits (already sorted by priority in caller, usually)
    # But caller sorts *after* calling this? No, caller sorts `visits` list in place?
    # Actually caller logic: `visits.sort(...)` happens inside `select_visits_cp_sat`.
    # We should trust the order passed in is decent, or sort here if we want.
    # The caller sorts `visits` at line ~120. We inject this call later?
    # Ah, I need to make sure I call this function *after* the sort in the main function.
    # The replacement puts it before `model` setup. The sort is before that. So list IS sorted.

    for i, v in enumerate(visits):
        req_res = getattr(v, "required_researchers", 1) or 1
        part = getattr(v, "part_of_day", None)
        if not part:
            continue

        allowed_days = _allowed_day_indices_for_visit(week_monday, v, today=today)
        if not allowed_days:
            continue

        # Try finding a valid day and team
        # Greedy strategy: First valid day that can host the full team

        assigned_team = []
        chosen_day = -1

        for d in allowed_days:
            # Try to form a team for day d
            potential_team = []

            for j, u in enumerate(users):
                uid = getattr(u, "id", None)
                if uid is None:
                    continue

                # Check 1: Already busy on day d?
                if d in user_busy[uid]:
                    continue

                # Check 2: Weekly Capacity > 0
                if user_rem_weekly.get(uid, 0) <= 0:
                    continue

                # Check 3: Daypart Capacity
                # Check Dedicated or Flex
                u_dp = user_rem_daypart.get(uid, {})
                has_dedicated = u_dp.get(part, 0) > 0
                has_flex = u_dp.get("Flex", 0) > 0

                if not (has_dedicated or has_flex):
                    continue

                # Check 4: Qualification / Preference
                if not _qualifies_user_for_visit(u, v):
                    continue

                # Valid candidate
                potential_team.append(j)

                if len(potential_team) == req_res:
                    break

            if len(potential_team) == req_res:
                # Found a fit!
                assigned_team = potential_team
                chosen_day = d
                break

        if assigned_team:
            # Commit
            scheduled_indices.add(i)
            visit_days[i] = chosen_day
            visit_assigns[i] = assigned_team

            for u_idx in assigned_team:
                u = users[u_idx]
                uid = getattr(u, "id", 0)

                # Update State
                user_rem_weekly[uid] -= 1
                user_busy[uid].add(chosen_day)

                u_dp = user_rem_daypart.get(uid, {})
                if u_dp.get(part, 0) > 0:
                    u_dp[part] -= 1
                else:
                    u_dp["Flex"] -= 1

    return scheduled_indices, visit_days, visit_assigns


def _build_weekly_skip_reason_nl(v: Visit, reason_code: str, week_monday: date) -> str:
    """Build a Dutch human-readable explanation for why a visit was skipped."""
    week_num = week_monday.isocalendar().week
    from_d = getattr(v, "from_date", None)
    to_d = getattr(v, "to_date", None)
    part = getattr(v, "part_of_day", None) or "?"

    if reason_code == "geen_dagdeel":
        return "Geen dagdeel (Ochtend/Dag/Avond) ingesteld op dit bezoek."

    if reason_code == "protocol_volgorde":
        return (
            "Een eerder bezoek in de protocolvolgorde voor dit cluster moet "
            "eerst worden ingepland."
        )

    if reason_code == "geen_dag_in_venster":
        return (
            f"Het uitvoeringsvenster ({from_d} t/m {to_d}) "
            f"valt niet op een werkdag in week {week_num}."
        )

    if reason_code == "geen_gekwalificeerde_onderzoekers":
        return (
            f"Geen gekwalificeerde onderzoekers beschikbaar voor dit bezoek "
            f"(dagdeel: {part})."
        )

    if reason_code == "onderzoekers_vergrendeld_niet_gekwalificeerd":
        locked_names = ", ".join(
            getattr(u, "full_name", None) or f"#{getattr(u, 'id', '?')}"
            for u in (getattr(v, "researchers", []) or [])
        )
        return (
            f"De vastgezette onderzoekers ({locked_names}) zijn niet gekwalificeerd "
            f"voor dit bezoek. Verwijder de onderzoekers-vergrendeling of wijs "
            "gekwalificeerde onderzoekers toe."
        )

    if reason_code == "onderzoekers_vergrendeld_geen_capaciteit":
        locked_names = ", ".join(
            getattr(u, "full_name", None) or f"#{getattr(u, 'id', '?')}"
            for u in (getattr(v, "researchers", []) or [])
        )
        return (
            f"De vastgezette onderzoekers ({locked_names}) hebben onvoldoende "
            f"capaciteit of zijn niet beschikbaar voor dagdeel '{part}' in week {week_num}. "
            "Pas de beschikbaarheid aan of verwijder de onderzoekers-vergrendeling."
        )

    # capaciteitsgebrek (default)
    return (
        f"Onvoldoende '{part}'-capaciteit beschikbaar in week {week_num}. "
        "Hogere-prioriteitsbezoeken hebben de beschikbare capaciteit opgebruikt."
    )


def _pre_solve_diagnose(
    *,
    v_map: dict,
    u_map: dict,
    x: dict,
    scheduled: dict,
    user_caps: dict,
    user_daypart_caps: dict,
    pre_blocked_slots: set,
    week_monday,
    today,
) -> None:
    """Log structured warnings for known infeasibility patterns before CP-SAT runs.

    This does NOT raise — it only logs so the developer can read the cause in
    the server output when CP-SAT returns INFEASIBLE.
    """
    from app.services.visit_planning_selection import _allowed_day_indices_for_visit

    issues: list[str] = []

    for i, v in v_map.items():
        vid = getattr(v, "id", i)
        vname = getattr(v, "name", None) or f"visit#{vid}"
        req = getattr(v, "required_researchers", 1) or 1

        # 1. No allowed days this week
        allowed_days = _allowed_day_indices_for_visit(week_monday, v, today=today)
        if not allowed_days:
            issues.append(f"  VISIT {vname} (id={vid}): geen toegestane dagen deze week")

        # 2. Fewer qualified researchers than required
        qualified_js = [j for j in u_map if (i, j) in x]
        if len(qualified_js) < req:
            issues.append(
                f"  VISIT {vname} (id={vid}): slechts {len(qualified_js)} gekwalificeerde "
                f"onderzoekers, maar {req} vereist"
            )

        # 3. researchers_locked: check capacity and availability of locked researchers
        if getattr(v, "researchers_locked", False) and getattr(v, "researchers", None):
            locked_user_ids = {getattr(u, "id", None) for u in v.researchers} - {None}
            if locked_user_ids:
                part = (getattr(v, "part_of_day", "") or "").strip()
                for j, u in u_map.items():
                    uid = getattr(u, "id", None)
                    if uid not in locked_user_ids:
                        continue
                    uname = getattr(u, "full_name", None) or f"user#{uid}"

                    # a. Check weekly capacity
                    cap = user_caps.get(uid, 0)
                    if cap <= 0:
                        issues.append(
                            f"  LOCKED {vname} (id={vid}): onderzoeker {uname} heeft "
                            f"0 weekcapaciteit (al vol of geen beschikbaarheid)"
                        )

                    # b. Check if ALL allowed days are pre-blocked for this researcher
                    if allowed_days and part:
                        blocked_days = {
                            d for d in allowed_days
                            if (uid, d, part) in pre_blocked_slots
                        }
                        if blocked_days == set(allowed_days):
                            issues.append(
                                f"  LOCKED {vname} (id={vid}): onderzoeker {uname} is op "
                                f"alle toegestane dagen al bezet in dagdeel '{part}' "
                                f"(pre_blocked_slots: {sorted(blocked_days)})"
                            )

                    # c. Check strict-mode day availability
                    dp_caps = user_daypart_caps.get(uid, {})
                    allowed_days_dict = dp_caps.get("days", {})
                    if allowed_days_dict and part and allowed_days:
                        allowed_days_for_part = set(allowed_days_dict.get(part, [0, 1, 2, 3, 4]))
                        feasible_days = set(allowed_days) & allowed_days_for_part
                        if not feasible_days:
                            issues.append(
                                f"  LOCKED {vname} (id={vid}): onderzoeker {uname} heeft "
                                f"geen beschikbaarheid op de toegestane dagen voor dagdeel "
                                f"'{part}' (beschikbaar: {sorted(allowed_days_for_part)}, "
                                f"toegestaan voor bezoek: {sorted(allowed_days)})"
                            )

    if issues:
        _logger.warning(
            "WeeklyPlanning pre-solve diagnose: mogelijke infeasibility-oorzaken:\n%s",
            "\n".join(issues),
        )
    else:
        _logger.info("WeeklyPlanning pre-solve diagnose: geen bekende harde conflicten gevonden")


async def select_visits_cp_sat(
    db: AsyncSession,
    week_monday: date,
    # Optional overrides for simulation
    visits: list[Visit] | None = None,
    users: list[User] | None = None,
    user_caps: dict[int, int] | None = None,
    user_daypart_caps: dict[int, dict[str, int]] | None = None,
    timeout_seconds: float | None = None,
    include_travel_time: bool = True,
    ignore_existing_assignments: bool = False,
    today: date | None = None,
) -> VisitSelectionResult:
    """
    Select visits and assign researchers using OR-Tools (CP-SAT).

    Optimizes for maximizing total priority weight of scheduled visits.


    Constraints:
    - Weekly capacity per user.
    - Daypart capacity per user (Dedicated + Flex).
    - Qualification rules.
    - Strict day coordination: All researchers on a visit must go on the same valid day.
    - Visit valid day indices.
    """
    from app.services.visit_planning_selection import (
        _allowed_day_indices_for_visit,
        _eligible_visits_for_week,
        _load_user_capacities,
        _load_user_daypart_capacities,
        _priority_key,
        _qualifies_user_for_visit,
        _load_all_users,
        _apply_existing_assignments_to_capacities,
        DAYPART_TO_AVAIL_FIELD,
    )

    # 1. Load Data
    week = week_monday.isocalendar().week

    if visits is None:
        visits = await _eligible_visits_for_week(db, week_monday)

    if users is None:
        users = await _load_all_users(db)

    # Ensure deterministic order for user list processing
    if users:
        users.sort(key=lambda u: getattr(u, "id", 0) or 0)

    if user_caps is None:
        user_caps = await _load_user_capacities(db, week)

    if user_daypart_caps is None:
        user_daypart_caps = await _load_user_daypart_capacities(db, week)

    # Pre-blocked day slots: researcher × day-index × daypart combinations that are
    # already occupied by a visit outside the solver pool (planning_locked or otherwise
    # already assigned with a concrete planned_date).  The OR-Tools daily constraint
    # only sees visits in v_map; without this, the solver can assign a second visit to
    # the same researcher on the same day/daypart as an already-locked visit.
    # Maps (researcher_id, day_index 0-4, daypart) -> True
    pre_blocked_slots: set[tuple[int, int, str]] = set()
    if db and not isinstance(db, list) and not ignore_existing_assignments:
        from sqlalchemy import select as _sa_select
        from sqlalchemy.orm import selectinload as _sil
        from app.models.visit import Visit as _Visit

        _preplanned_stmt = (
            _sa_select(_Visit)
            .where(
                _Visit.planned_week == week,
                _Visit.planned_date.isnot(None),
            )
            .options(_sil(_Visit.researchers))
        )
        _preplanned: list = (await db.execute(_preplanned_stmt)).scalars().unique().all()
        for _pv in _preplanned:
            _pdate = getattr(_pv, "planned_date", None)
            if _pdate is None:
                continue
            _d_idx = (_pdate - week_monday).days
            if _d_idx < 0 or _d_idx > 4:
                continue
            _part = (getattr(_pv, "part_of_day", "") or "").strip()
            if not _part:
                continue
            for _pu in getattr(_pv, "researchers", []) or []:
                _uid = getattr(_pu, "id", None)
                if _uid is not None:
                    pre_blocked_slots.add((_uid, _d_idx, _part))

    if (
        db and not isinstance(db, list) and not ignore_existing_assignments
    ):  # Hack: avoid calling valid db ops if it's a list (test mock)
        await _apply_existing_assignments_to_capacities(
            db, week, user_caps, user_daypart_caps
        )

    # Huismus pairing: load Pool 2 candidates (future provisional_week but window
    # overlaps this week). These are only scheduled as the second visit of a pair.
    _pairing_only_visit_ids: set[int] = set()
    if get_settings().feature_huismus_pairing and include_travel_time and db and not isinstance(db, list):
        from app.services.visit_planning_selection import _load_huismus_pairing_candidates
        pairing_cands = await _load_huismus_pairing_candidates(db, week_monday, week)
        existing_ids = {v.id for v in visits}
        new_cands = [v for v in pairing_cands if v.id not in existing_ids]
        _pairing_only_visit_ids = {v.id for v in new_cands if v.id is not None}
        visits = list(visits) + new_cands
        if new_cands:
            _logger.info(
                "huismus_pairing: loaded %d Pool-2 pairing candidates", len(new_cands)
            )

    # Filter out visits with no daypart
    # AND enforce "Sequential Order": If multiple visits for same protocol are present,
    # keep only the one with the Lowest visit_index.

    from collections import defaultdict

    protocol_groups = defaultdict(list)

    clean_visits = []
    skipped_visits = []
    # Maps visit_id -> reason_code for pre-solver skips
    skip_reason: dict[int, str] = {}

    # 1. Group by Protocol + Cluster
    for v in visits:
        pod = getattr(v, "part_of_day", None)
        if not pod or pod not in DAYPART_TO_AVAIL_FIELD:
            skipped_visits.append(v)
            if v.id is not None:
                skip_reason[v.id] = "geen_dagdeel"
            continue

        # Check Protocol Windows
        pvws = getattr(v, "protocol_visit_windows", []) or []
        if not pvws:
            # If no protocol info, treat as independent
            clean_visits.append(v)
            continue

        for pvw in pvws:
            protocol_groups[(pvw.protocol_id, v.cluster_id)].append(
                (pvw.visit_index, v)
            )

    # 2. Identify "Allowed" visits (lowest index per protocol)
    # A visit is rejected if it has a window that is NOT the lowest index for that protocol.
    # Wait, simple logic:
    # visits_to_reject = set()
    # For each protocol, find min_index. Reject any v that maps to index > min_index.

    visits_to_reject_ids = set()

    for pid, items in protocol_groups.items():
        if not items:
            continue

        # Sort by index
        items.sort(key=lambda x: x[0])
        min_index = items[0][0]

        for idx, v in items:
            if idx > min_index:
                visits_to_reject_ids.add(v.id)

    # 3. Re-build clean list
    final_visits = []
    for v in visits:
        pod = getattr(v, "part_of_day", None)
        # Skip if already skipped (invalid pod)
        if not pod or pod not in DAYPART_TO_AVAIL_FIELD:
            continue

        if v.id in visits_to_reject_ids:
            skipped_visits.append(v)
            if v.id is not None:
                skip_reason[v.id] = "protocol_volgorde"
            _logger.info(
                "Skipping out-of-order visit %s (Protocol constraint)",
                getattr(v, "id", None),
            )
        else:
            final_visits.append(v)

    visits = final_visits

    # 2. Model Setup
    model = cp_model.CpModel()

    # --- Variables ---

    # x[v_idx, u_idx]: Binary. 1 if user u assigned to visit v.
    x = {}

    # scheduled[v_idx]: Binary. 1 if visit v is scheduled.
    scheduled = {}

    # visit_day[v_idx, d]: Binary. 1 if visit v is done on day d (0..4).
    visit_day = {}

    # flex_alloc[u_idx, p]: Integer. Amount of Flex capacity user u uses for daypart p.
    # We define strictly: flex_alloc[u, p] >= 0.
    flex_alloc = {}

    # active_on_day[u_idx, d]: Binary. 1 if user u has ANY visit on day d.
    # Used to enforce "At most 1 visit per day per user" (Simplified for initial parity).
    # Wait, the requirement is "users assigned to the same visit must go on the same day".
    # And "user can only do Max 1 visit on Day d" (implicit from legacy per_user_day_schedule).

    # active_assignment[v_idx, u_idx, d]: Binary. User u does visit v on day d.
    # active_assignment[v, u, d] <=> x[v, u] AND visit_day[v, d]
    active_assignment = {}

    # Helper lookups
    # Sort visits by priority key to establish rank-based weights
    # This ensures the solver respects deadlines and tie-breakers similar to legacy heuristic
    # Locked visits get the highest greedy priority so the warm-start hint includes them,
    # preventing CP-SAT from needing to discover the swap within the time limit.
    visits.sort(key=lambda v: (
        0 if (getattr(v, "researchers_locked", False) and getattr(v, "researchers", None)) else 1,
        _priority_key(week_monday, v),
    ))

    v_map = {i: v for i, v in enumerate(visits)}
    u_map = {i: u for i, u in enumerate(users)}

    # Identify pairing-only indices (Pool 2 Huismus candidates)
    pairing_only_indices: set[int] = {
        i for i, v in v_map.items() if getattr(v, "id", None) in _pairing_only_visit_ids
    }

    # Pre-fetch cluster-to-cluster travel times for consecutive-daypart proximity
    # constraint (strict availability mode only).
    # Consecutive pairs: Ochtend→Dag and Dag→Avond (same day), Avond→Ochtend (overnight).
    _CONSEC_SAME_DAY: set[tuple[str, str]] = {("Ochtend", "Dag"), ("Dag", "Avond")}
    _OVERNIGHT_PAIR: tuple[str, str] = ("Avond", "Ochtend")
    consec_cluster_travel: dict[tuple[str, str], int] = {}

    if include_travel_time and get_settings().feature_strict_availability:
        from app.services import travel_time as _tt_consec

        _consec_pairs: list[tuple[str, str]] = []
        _consec_pair_indices: dict[tuple[str, str], list[tuple[int, int]]] = {}

        for i1, v1 in v_map.items():
            p1 = (getattr(v1, "part_of_day", None) or "").strip()
            addr1 = _full_addr_for_travel_time(getattr(v1, "cluster", None))
            if not addr1 or not p1:
                continue
            for i2, v2 in v_map.items():
                if i1 == i2:
                    continue
                p2 = (getattr(v2, "part_of_day", None) or "").strip()
                if (p1, p2) not in _CONSEC_SAME_DAY and (p1, p2) != _OVERNIGHT_PAIR:
                    continue
                addr2 = _full_addr_for_travel_time(getattr(v2, "cluster", None))
                if not addr2:
                    continue
                key = (addr1, addr2)
                _consec_pairs.append(key)
                _consec_pair_indices.setdefault(key, []).append((i1, i2))

        if _consec_pairs:
            consec_cluster_travel = await _tt_consec.get_travel_minutes_batch(
                _consec_pairs, db=db
            )

    part_labels = ["Ochtend", "Dag", "Avond"]

    # Weights based on rank: First items (highest priority/deadline) get highest weight
    # We use a large multiplier to ensure strictly respecting the order is better than many low-priority items?
    # actually, simple linear rank is enough if we want to "Maximize number of high priority items".
    # But Sum(Rank * Bool) -> Maximize total rank.
    # Legacy: Iterate and pick if possible. This is "Hierarchical".
    # Solver: Global optimization.
    # To mimic "Pick A over B", Weight(A) > Weight(B).
    # To mimic "Pick A over B+C", Weight(A) > Weight(B) + Weight(C).
    # But usually we just want "Pick most important ones".
    # Let's use simple linear rank for now.
    # UPDATE: We must ensure Reward > (Travel Cost + Load Cost) to failing to schedule.
    # Max Travel ~ 120. Max Load Cost ~ 30 * N^2.
    # Use a large base.
    BASE_REWARD = 10000
    # Locked visits get a reward larger than the sum of all other visits combined,
    # so the solver always prefers assigning the locked researcher to their locked
    # visit over any other combination.
    LOCKED_REWARD = BASE_REWARD * (len(v_map) + 1) * 2
    visit_weights = {i: BASE_REWARD + (len(visits) - i) * 100 for i in v_map}
    for i, v in v_map.items():
        if getattr(v, "researchers_locked", False) and getattr(v, "researchers", None):
            locked_ids = {getattr(u, "id", None) for u in v.researchers} - {None}
            if locked_ids:
                visit_weights[i] = LOCKED_REWARD + (len(visits) - i) * 100
                _logger.info(
                    "LOCKED_REWARD applied: visit_id=%s weight=%d locked_user_ids=%s",
                    getattr(v, "id", i),
                    visit_weights[i],
                    locked_ids,
                )
    # Pool 2 (pairing-only) visits have no independent reward — only the pairing bonus
    for i in pairing_only_indices:
        visit_weights[i] = 0

    # --- Constraints ---

    # Tracks (i, j) pairs where researcher j is locked to visit i.
    # These must bypass the travel-time hard cutoff.
    locked_assignments: set[tuple[int, int]] = set()

    for i, v in v_map.items():
        scheduled[i] = model.NewBoolVar(f"scheduled_{i}")

        # 2a. Visit Day Logic
        allowed_indices = _allowed_day_indices_for_visit(week_monday, v, today=today)
        if not allowed_indices:
            # Cannot be scheduled if no allowed days
            model.Add(scheduled[i] == 0)
        else:
            # Create day booleans only for allowed days
            days_vars = []
            for d in range(5):
                visit_day[i, d] = model.NewBoolVar(f"visit_{i}_day_{d}")
                if d in allowed_indices:
                    days_vars.append(visit_day[i, d])
                else:
                    model.Add(visit_day[i, d] == 0)

            # If scheduled, must pick exactly one day
            model.Add(sum(days_vars) == scheduled[i])

        # 2b. Researcher Assignment
        req = getattr(v, "required_researchers", 1) or 1

        assigned_vars = []
        for j, u in u_map.items():
            qualified = _qualifies_user_for_visit(u, v)
            if qualified:
                x[i, j] = model.NewBoolVar(f"x_{i}_{j}")
                assigned_vars.append(x[i, j])

                # Active Assignment logic: x[i, j] AND visit_day[i, d]
                for d in range(5):
                    active_assignment[i, j, d] = model.NewBoolVar(f"active_{i}_{j}_{d}")
                    model.Add(active_assignment[i, j, d] <= x[i, j])
                    if (i, d) in visit_day:
                        model.Add(active_assignment[i, j, d] <= visit_day[i, d])
                        model.Add(
                            active_assignment[i, j, d] >= x[i, j] + visit_day[i, d] - 1
                        )
                    else:
                        model.Add(active_assignment[i, j, d] == 0)
            else:
                pass

        # If scheduled, must assign exactly 'req' researchers
        if assigned_vars:
            model.Add(sum(assigned_vars) == req * scheduled[i])
        else:
            model.Add(scheduled[i] == 0)

        # 2b-post. Researchers-locked soft constraint.
        # If the visit has client-specified researchers, force exactly those users to be
        # assigned (if the visit is scheduled) and block all others.
        # The visit is NOT forced to be scheduled — if the locked researchers lack
        # capacity or availability the solver simply skips it (scheduled == 0) and a
        # diagnostic warning is emitted in the result.
        if getattr(v, "researchers_locked", False) and getattr(v, "researchers", None):
            locked_user_ids = {getattr(u, "id", None) for u in v.researchers}
            locked_user_ids.discard(None)
            if locked_user_ids:
                allowed_days = _allowed_day_indices_for_visit(week_monday, v, today=today)
                part = (getattr(v, "part_of_day", "") or "").strip()
                for j, u in u_map.items():
                    uid = getattr(u, "id", None)
                    if uid not in locked_user_ids:
                        if (i, j) in x:
                            model.Add(x[i, j] == 0)
                        continue
                    # Locked researcher diagnostics
                    cap = user_caps.get(uid, 0)
                    dp_caps = user_daypart_caps.get(uid, {})
                    dedicated = dp_caps.get(part, 0)
                    flex = dp_caps.get("Flex", 0)
                    uname = getattr(u, "full_name", None) or f"user#{uid}"
                    qualified = (i, j) in x
                    _logger.info(
                        "LOCKED constraint: visit_id=%s user=%s qualified=%s "
                        "weekly_cap=%d dedicated_%s=%d flex=%d allowed_days=%s",
                        getattr(v, "id", i), uname, qualified,
                        cap, part, dedicated, flex, allowed_days,
                    )
                    if qualified:
                        model.Add(x[i, j] == scheduled[i])
                        locked_assignments.add((i, j))

    # 2c-pre. Huismus pairing variables (feature_huismus_pairing).
    #
    # pair_saves[i1, i2, j]: BoolVar — 1 when researcher j executes both Huismus
    # visits i1 (Pool 1) and i2 (Pool 2) on the same day.  Each active pair saves
    # 1 capacity unit for the researcher (the pair counts as a single visit).
    pair_saves: dict[tuple, object] = {}
    pair_day_active: dict[tuple, object] = {}  # (i1, i2, j, d) → BoolVar, 1 when pair active on day d
    valid_huismus_pair_indices: list[tuple[int, int]] = []
    pool2_pair_indices: set[tuple[int, int]] = set()  # subset where i2 is a Pool-2 visit (gets cap saving)

    if get_settings().feature_huismus_pairing:
        from app.services.visit_planning_selection import _is_huismus_nest_visit as _is_huismus_v

        pool1_huismus: set[int] = {
            i for i, v in v_map.items()
            if i not in pairing_only_indices and _is_huismus_v(v)
        }

        # Fetch cluster-to-cluster travel times for all candidate pairs:
        #   - Pool1 × Pool2  (bring a future-week visit into the current week)
        #   - Pool1 × Pool1  (two visits already in the current-week pool → same-day bonus)
        max_travel = get_settings().huismus_pairing_max_travel_minutes
        _h_pair_addr_map: dict[tuple, list[tuple[int, int]]] = {}
        _h_pairs_to_fetch: list[tuple[str, str]] = []

        def _enqueue_huismus_pair(i1: int, i2: int) -> None:
            v1 = v_map[i1]
            v2 = v_map[i2]
            p1 = (getattr(v1, "part_of_day", None) or "").strip()
            p2 = (getattr(v2, "part_of_day", None) or "").strip()
            if p1 != p2 or not p1:
                return  # Must be the same daypart
            addr1 = _full_addr_for_travel_time(getattr(v1, "cluster", None))
            addr2 = _full_addr_for_travel_time(getattr(v2, "cluster", None))
            if not addr1 or not addr2:
                return
            key = (addr1, addr2)
            _h_pairs_to_fetch.append(key)
            _h_pair_addr_map.setdefault(key, []).append((i1, i2))

        # Pool1 × Pool2 pairs
        for i1 in pool1_huismus:
            for i2 in pairing_only_indices:
                _enqueue_huismus_pair(i1, i2)

        # Pool1 × Pool1 pairs (both visits already in the regular pool)
        pool1_list = sorted(pool1_huismus)
        for idx_a, i1 in enumerate(pool1_list):
            for i2 in pool1_list[idx_a + 1:]:
                _enqueue_huismus_pair(i1, i2)

        if _h_pairs_to_fetch:
            from app.services import travel_time as _tt_h
            _h_travel = await _tt_h.get_travel_minutes_batch(_h_pairs_to_fetch, db=db)
            for key, mins in _h_travel.items():
                if mins <= max_travel:
                    for (i1, i2) in _h_pair_addr_map.get(key, []):
                        valid_huismus_pair_indices.append((i1, i2))
                        if i2 in pairing_only_indices:
                            pool2_pair_indices.add((i1, i2))

        _logger.info(
            "huismus_pairing: %d Pool-1 Huismus, %d Pool-2 candidates, %d valid pairs (≤%d min)",
            len(pool1_huismus),
            len(pairing_only_indices),
            len(valid_huismus_pair_indices),
            max_travel,
        )

        # Create pair_saves[i1, i2, j] for every valid pair × every user
        for (i1, i2) in valid_huismus_pair_indices:
            for j in u_map:
                if (i1, j) not in x or (i2, j) not in x:
                    continue
                ps = model.NewBoolVar(f"hps_{i1}_{i2}_{j}")
                pair_saves[i1, i2, j] = ps

                day_vars_for_pair = []
                for d in range(5):
                    if (i1, j, d) not in active_assignment or (i2, j, d) not in active_assignment:
                        continue
                    pad = model.NewBoolVar(f"hpad_{i1}_{i2}_{j}_{d}")
                    # pad ⟺ active_assignment[i1,j,d] ∧ active_assignment[i2,j,d]
                    model.AddBoolAnd(
                        [active_assignment[i1, j, d], active_assignment[i2, j, d]]
                    ).OnlyEnforceIf(pad)
                    model.AddBoolOr(
                        [active_assignment[i1, j, d].Not(), active_assignment[i2, j, d].Not()]
                    ).OnlyEnforceIf(pad.Not())
                    pair_day_active[i1, i2, j, d] = pad
                    day_vars_for_pair.append(pad)

                if day_vars_for_pair:
                    model.AddBoolOr(day_vars_for_pair).OnlyEnforceIf(ps)
                    model.AddBoolAnd([dv.Not() for dv in day_vars_for_pair]).OnlyEnforceIf(
                        ps.Not()
                    )
                else:
                    model.Add(ps == 0)

        # At most 1 researcher can activate a given pair (implied by visit-assignment
        # uniqueness, but stating it explicitly lets CP-SAT tighten its bound fast and
        # prevents objective inflation from per-researcher pair_saves variables).
        for (i1, i2) in valid_huismus_pair_indices:
            pair_vars_for_pair = [
                pair_saves[i1, i2, j] for j in u_map if (i1, i2, j) in pair_saves
            ]
            if len(pair_vars_for_pair) > 1:
                model.Add(sum(pair_vars_for_pair) <= 1)

        # Global LP-tightening constraint: the total number of active pairs is
        # bounded by the number of Pool-1 visits (each Pool-1 visit can be in
        # at most one pair).  Without this, the LP relaxation allows all
        # pair_saves variables to be fractionally 1 simultaneously, inflating
        # the bound to ~(n_pairs × HUISMUS_PAIR_BONUS) and preventing CP-SAT
        # from closing the gap within the time limit.
        all_pair_save_vars = list(pair_saves.values())
        if all_pair_save_vars:
            model.Add(sum(all_pair_save_vars) <= len(pool1_huismus))

        # Pool 2 visits may ONLY be scheduled as part of a valid pair
        for i2 in pairing_only_indices:
            pair_vars_for_i2 = [
                pair_saves[i1, pi2, j]
                for (i1, pi2) in valid_huismus_pair_indices
                if pi2 == i2
                for j in u_map
                if (i1, pi2, j) in pair_saves
            ]
            if pair_vars_for_i2:
                model.Add(scheduled[i2] <= sum(pair_vars_for_i2))
            else:
                # No valid pool-1 partner found → cannot schedule
                model.Add(scheduled[i2] == 0)

    # 2c. User Capacity Constraints

    # Helper: ensure assigning to allowed days only (Strict Mode)
    strict_mode = get_settings().feature_strict_availability

    for j, u in u_map.items():
        uid = getattr(u, "id", None)
        if uid is None:
            continue

        # Weekly Max
        cap_max = user_caps.get(uid, 0)
        user_assignments = [x.get((i, j)) for i in v_map if (i, j) in x]
        # Each active Huismus pair saves 1 capacity unit: two visits done together on the
        # same day count as 1 slot.  The per-day limit (sum(h_pairs_this_day) <= 1) already
        # caps savings at 1 per day, so this is safe for both Pool1×Pool2 and Pool1×Pool1.
        user_pair_saves = [
            pair_saves[i1, i2, j]
            for (i1, i2) in valid_huismus_pair_indices
            if (i1, i2, j) in pair_saves
        ]
        if user_pair_saves:
            model.Add(sum(user_assignments) - sum(user_pair_saves) <= cap_max)
        else:
            model.Add(sum(user_assignments) <= cap_max)

        # Daypart Max & Flex
        dp_caps = user_daypart_caps.get(uid, {})
        flex_max = dp_caps.get("Flex", 0)

        total_flex_usage = []

        for part in part_labels:
            dedicated = dp_caps.get(part, 0)

            part_assignments = [
                x[i, j]
                for i in v_map
                if (i, j) in x and getattr(v_map[i], "part_of_day", None) == part
            ]

            if not part_assignments:
                continue

            fa = model.NewIntVar(0, 50, f"flex_{j}_{part}")
            flex_alloc[j, part] = fa
            total_flex_usage.append(fa)

            # Each active pair saves 1 daypart slot (bounded by per-day pair limit)
            part_pair_saves = [
                pair_saves[i1, i2, j]
                for (i1, i2) in valid_huismus_pair_indices
                if (i1, i2, j) in pair_saves
                and getattr(v_map[i1], "part_of_day", None) == part
                and getattr(v_map[i2], "part_of_day", None) == part
            ]
            if part_pair_saves:
                model.Add(sum(part_assignments) - sum(part_pair_saves) <= dedicated + fa)
            else:
                model.Add(sum(part_assignments) <= dedicated + fa)

        if total_flex_usage:
            model.Add(sum(total_flex_usage) <= flex_max)

        # Restrict assignment precisely to allowed days per daypart (Strict Mode)
        if strict_mode:
            allowed_days_dict = dp_caps.get("days", {})
            for part in part_labels:
                allowed_days_for_part = allowed_days_dict.get(part, [0, 1, 2, 3, 4])

                # If they have 0 dedicated slots, their entire capacity relies on Flex.
                # In that case, we can't restrict their days by the 'part' schedule directly,
                # but if they DO have dedicated slots from the DB, the 'days' array will hold them.
                # Actually, in strict mode, *all* availability comes from scheduled slots.
                # There is no generic "Flex" in strict mode unless unhandled.
                # Therefore, if day d is NOT in allowed_days_for_part, we must forbid assigning
                # this part on day d.

                for d in range(5):
                    if d not in allowed_days_for_part:
                        forbidden_vars = [
                            active_assignment[i, j, d]
                            for i in v_map
                            if (i, j, d) in active_assignment
                            and getattr(v_map[i], "part_of_day", None) == part
                        ]
                        for f_var in forbidden_vars:
                            model.Add(f_var == 0)

    # 2d. Strict Day Coordination
    # In strict availability mode researchers may do 2 visits per day (double visits).
    max_visits_per_day = 2 if get_settings().feature_strict_availability else 1
    for j in u_map:
        uid = getattr(u_map[j], "id", None)
        for d in range(5):
            # 1. Total visits per day limit
            active_vars = [
                active_assignment[i, j, d]
                for i in v_map
                if (i, j, d) in active_assignment
            ]
            if active_vars:
                # Allow 1 extra visit if there is exactly 1 active Huismus pair on this day.
                # We cap the bonus at 1 (a researcher may have at most 1 pair per day).
                h_pairs_this_day = [
                    pair_day_active[i1, i2, j, d]
                    for (i1, i2) in valid_huismus_pair_indices
                    if (i1, i2, j, d) in pair_day_active
                ]
                if h_pairs_this_day:
                    model.Add(sum(h_pairs_this_day) <= 1)  # at most 1 pair per researcher per day
                    model.Add(sum(active_vars) <= max_visits_per_day + sum(h_pairs_this_day))
                else:
                    model.Add(sum(active_vars) <= max_visits_per_day)

            # 2. Strict Daypart Exclusion: At most 1 visit per daypart per day
            # (relaxed for Huismus pairs: two paired visits in the same daypart count as 1)
            for part in part_labels:
                part_active_vars = [
                    active_assignment[i, j, d]
                    for i in v_map
                    if (i, j, d) in active_assignment
                    and getattr(v_map[i], "part_of_day", None) == part
                ]
                if part_active_vars:
                    # If this researcher already has a pre-planned (locked) visit on
                    # this day in this daypart, forbid any solver visit here entirely.
                    if uid is not None and (uid, d, part) in pre_blocked_slots:
                        for var in part_active_vars:
                            model.Add(var == 0)
                        continue
                    h_pairs_this_daypart = [
                        pair_day_active[i1, i2, j, d]
                        for (i1, i2) in valid_huismus_pair_indices
                        if (i1, i2, j, d) in pair_day_active
                        and getattr(v_map[i1], "part_of_day", None) == part
                    ]
                    if h_pairs_this_daypart:
                        model.Add(sum(h_pairs_this_daypart) <= 1)  # at most 1 pair per daypart per day
                        model.Add(sum(part_active_vars) <= 1 + sum(h_pairs_this_daypart))
                    else:
                        model.Add(sum(part_active_vars) <= 1)

    # 2e. Consecutive-daypart proximity constraint (strict availability mode only).
    # When a researcher is assigned two visits in consecutive dayparts — either on
    # the same day (Ochtend→Dag, Dag→Avond) or overnight (Avond on day D →
    # Ochtend on day D+1) — the clusters must be ≤30 minutes apart.  If the
    # pre-fetched travel time exceeds 30 minutes, forbid that combination.
    if get_settings().feature_strict_availability and consec_cluster_travel:
        for i1, v1 in v_map.items():
            p1 = (getattr(v1, "part_of_day", None) or "").strip()
            addr1 = _full_addr_for_travel_time(getattr(v1, "cluster", None))
            if not addr1 or not p1:
                continue
            for i2, v2 in v_map.items():
                if i1 == i2:
                    continue
                p2 = (getattr(v2, "part_of_day", None) or "").strip()
                is_same_day = (p1, p2) in _CONSEC_SAME_DAY
                is_overnight = (p1, p2) == _OVERNIGHT_PAIR
                if not is_same_day and not is_overnight:
                    continue
                addr2 = _full_addr_for_travel_time(getattr(v2, "cluster", None))
                if not addr2:
                    continue
                travel = consec_cluster_travel.get((addr1, addr2))

                if travel is None:
                    continue

                # We always log if it's evaluated for a researcher pair, but let's log the raw truth first
                # Actually, only log if >30 explicitly
                if travel <= 30:
                    continue

                # Travel time exceeds 30 min: forbid assigning the same researcher
                # to both visits in this consecutive order.
                for j in u_map:
                    if (i1, j) not in x or (i2, j) not in x:
                        continue
                    if is_same_day:
                        for d in range(5):
                            if (i1, j, d) in active_assignment and (
                                i2,
                                j,
                                d,
                            ) in active_assignment:
                                model.Add(
                                    active_assignment[i1, j, d]
                                    + active_assignment[i2, j, d]
                                    <= 1
                                )
                    else:  # overnight: v1 is Avond on day d, v2 is Ochtend on day d+1
                        for d in range(4):
                            has_d = (i1, j, d) in active_assignment
                            has_next_d = (i2, j, d + 1) in active_assignment

                            if has_d and has_next_d:
                                model.Add(
                                    active_assignment[i1, j, d]
                                    + active_assignment[i2, j, d + 1]
                                    <= 1
                                )

    # --- Objective ---
    obj_terms = []

    # Load Balancing Weight
    # Keep this the least important soft constraint.
    LOAD_BALANCE_WEIGHT = 1

    # Travel time penalties (minutes) and hard cutoff.
    # Weight=2 means a 30-minute trip costs 60 points (slightly more than large-team penalty).
    TRAVEL_TIME_WEIGHT = 2
    settings = get_settings()
    TRAVEL_TIME_HARD_LIMIT = settings.constraint_max_travel_time_minutes

    # Optimization: Check if we have travel_time service available (might be missing in tests if not mocked global?)
    # We imported it locally to be safe
    from app.services import travel_time

    travel_costs = {}

    if include_travel_time:
        # Helper to pre-calculate travel times for valid pairs
        # We only care about (i, j) pairs that are qualified/preferred
        pairs_to_check: list[tuple[str, str]] = []
        pair_to_indices: dict[tuple[str, str], list[tuple[int, int]]] = {}

        # Coördinaten per adresstring voor Haversine-fallback (geen postcode-zones nodig)
        addr_to_coords: dict[str, tuple[float, float]] = {}

        for i, v in v_map.items():
            cluster = getattr(v, "cluster", None)
            dest = getattr(cluster, "address", None)
            if not dest:
                continue

            dest = dest.strip()
            # 1. Check for Decimal Coordinates: Number, Number
            is_decimal = bool(re.match(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$", dest))
            # 2. Check for DMS Coordinates: Starts with digit, contains degree symbol
            is_dms = bool(re.match(r"^\d+°", dest))

            is_coords = is_decimal or is_dms

            if not is_coords:
                project = getattr(cluster, "project", None)
                loc = getattr(project, "location", None)
                if loc:
                    dest = f"{dest}, {loc}"

            # Sla opgeslagen coördinaten op voor Haversine-fallback
            c_lat = getattr(cluster, "lat", None)
            c_lon = getattr(cluster, "lon", None)
            if c_lat is not None and c_lon is not None:
                addr_to_coords[dest] = (c_lat, c_lon)

            for j, u in u_map.items():
                if _qualifies_user_for_visit(u, v):
                    origin = getattr(u, "address", None)
                    if not origin:
                        origin = getattr(u, "city", None)

                    if origin:
                        # Sla coördinaten van onderzoeker op voor Haversine-fallback
                        u_lat = getattr(u, "lat", None)
                        u_lon = getattr(u, "lon", None)
                        if u_lat is not None and u_lon is not None:
                            addr_to_coords[origin] = (u_lat, u_lon)

                        key = (origin, dest)
                        pairs_to_check.append(key)
                        if key not in pair_to_indices:
                            pair_to_indices[key] = []
                        pair_to_indices[key].append((i, j))

        # Parallel Fetch via Google Maps (gecached)
        if pairs_to_check:
            batch_results = await travel_time.get_travel_minutes_batch(
                pairs_to_check, db=db
            )
            # Map back to indices
            for (origin, dest), mins in batch_results.items():
                indices_list = pair_to_indices.get((origin, dest), [])
                for i, j in indices_list:
                    travel_costs[i, j] = mins

            # Haversine-fallback voor paren zonder Google Maps resultaat
            # (bijv. geen API-key of cache miss). Beter dan postcode-zones:
            # Lelystad (82xx) en Almere (13xx) zijn dichtbij maar postcodegewijs ver.
            for key, indices_list in pair_to_indices.items():
                origin, dest = key
                if any((i, j) not in travel_costs for i, j in indices_list):
                    o_coords = addr_to_coords.get(origin)
                    d_coords = addr_to_coords.get(dest)
                    if o_coords and d_coords:
                        mins = travel_time.haversine_minutes(*o_coords, *d_coords)
                        for i, j in indices_list:
                            if (i, j) not in travel_costs:
                                travel_costs[i, j] = mins

    for i, v in v_map.items():
        base_val = visit_weights[i]
        obj_terms.append(scheduled[i] * base_val)
        for j, u in u_map.items():
            if (i, j) in x:
                # Penalty for Travel Time
                cost = travel_costs.get((i, j), 0)
                if cost > 0:
                    if cost > TRAVEL_TIME_HARD_LIMIT:
                        if (i, j) in locked_assignments:
                            # Admin explicitly locked this researcher: respect the choice
                            # even if travel time exceeds the hard limit. Log a warning
                            # so the planner is aware.
                            _logger.warning(
                                "Locked researcher (visit_id=%s, user_id=%s) exceeds "
                                "travel hard limit (%d min > %d min) — hard limit bypassed.",
                                getattr(v_map[i], "id", i),
                                getattr(u_map[j], "id", j),
                                cost,
                                TRAVEL_TIME_HARD_LIMIT,
                            )
                        else:
                            model.Add(x[i, j] == 0)
                            continue
                    obj_terms.append(x[i, j] * -(cost * TRAVEL_TIME_WEIGHT))

    # Huismus pairing bonus: reward the solver for forming a valid Huismus pair
    if valid_huismus_pair_indices and pair_saves:
        HUISMUS_PAIR_BONUS = get_settings().huismus_pairing_bonus
        for (i1, i2) in valid_huismus_pair_indices:
            for j in u_map:
                if (i1, i2, j) in pair_saves:
                    obj_terms.append(pair_saves[i1, i2, j] * HUISMUS_PAIR_BONUS)

    # Load Balancing Penalty (Quadratic)
    # For each user, sum of assignments^2

    # 3. Consecutive Travel Penalty (Soft Constraint)
    # If the user is assigned consecutive visits (same day or overnight), penalize the
    # travel time between them to encourage tighter routing.
    # We only apply this if the travel time is <= 30 mins (since > 30 is forbidden).
    if (
        settings.feature_strict_availability
        and settings.constraint_consecutive_travel_penalty
        and consec_cluster_travel
    ):
        CONSEC_PENALTY_WEIGHT = settings.constraint_consecutive_travel_penalty_weight

        for i1, v1 in v_map.items():
            p1 = (getattr(v1, "part_of_day", None) or "").strip()
            addr1 = _full_addr_for_travel_time(getattr(v1, "cluster", None))
            if not addr1 or not p1:
                continue

            for i2, v2 in v_map.items():
                if i1 == i2:
                    continue
                p2 = (getattr(v2, "part_of_day", None) or "").strip()
                is_same_day = (p1, p2) in _CONSEC_SAME_DAY
                is_overnight = (p1, p2) == _OVERNIGHT_PAIR
                if not is_same_day and not is_overnight:
                    continue

                addr2 = _full_addr_for_travel_time(getattr(v2, "cluster", None))
                if not addr2:
                    continue

                travel = consec_cluster_travel.get((addr1, addr2))
                # Only penalize if there is actual travel time (and it's valid <=30 mins)
                if travel is None or travel == 0 or travel > 30:
                    continue

                for j in u_map:
                    if (i1, j) not in x or (i2, j) not in x:
                        continue

                    if is_same_day:
                        for d in range(5):
                            if (i1, j, d) in active_assignment and (
                                i2,
                                j,
                                d,
                            ) in active_assignment:
                                both_active = model.NewBoolVar(
                                    f"consec_{i1}_{i2}_{j}_{d}"
                                )
                                model.AddBoolAnd(
                                    [
                                        active_assignment[i1, j, d],
                                        active_assignment[i2, j, d],
                                    ]
                                ).OnlyEnforceIf(both_active)
                                model.AddBoolOr(
                                    [
                                        active_assignment[i1, j, d].Not(),
                                        active_assignment[i2, j, d].Not(),
                                    ]
                                ).OnlyEnforceIf(both_active.Not())
                                obj_terms.append(
                                    both_active * -(travel * CONSEC_PENALTY_WEIGHT)
                                )

                    else:  # overnight
                        for d in range(4):
                            if (i1, j, d) in active_assignment and (
                                i2,
                                j,
                                d + 1,
                            ) in active_assignment:
                                both_active = model.NewBoolVar(
                                    f"consec_overnight_{i1}_{i2}_{j}_{d}"
                                )
                                model.AddBoolAnd(
                                    [
                                        active_assignment[i1, j, d],
                                        active_assignment[i2, j, d + 1],
                                    ]
                                ).OnlyEnforceIf(both_active)
                                model.AddBoolOr(
                                    [
                                        active_assignment[i1, j, d].Not(),
                                        active_assignment[i2, j, d + 1].Not(),
                                    ]
                                ).OnlyEnforceIf(both_active.Not())
                                obj_terms.append(
                                    both_active * -(travel * CONSEC_PENALTY_WEIGHT)
                                )

    for j, u in u_map.items():
        # User assignments across all visits
        u_vars = [x[i, j] for i in v_map if (i, j) in x]
        if not u_vars:
            continue

        load_var = model.NewIntVar(0, len(visits), f"load_{j}")
        model.Add(load_var == sum(u_vars))

        load_sq = model.NewIntVar(0, len(visits) ** 2, f"load_sq_{j}")
        model.AddMultiplicationEquality(load_sq, [load_var, load_var])

        # Load Balancing Weighted by Percentage Utilization
        # Previous: load_sq * -LOAD_BALANCE_WEIGHT
        # New: load_sq * - (LOAD_BALANCE_WEIGHT * 5 / Capacity)

        cap_max = user_caps.get(
            getattr(u, "id", None) or 0, 5
        )  # Default to 5 if unknown
        if cap_max < 1:
            cap_max = 1

        weighted_penalty = int(LOAD_BALANCE_WEIGHT * 5 / cap_max)

        obj_terms.append(load_sq * -weighted_penalty)

        # 4. Large Team Visit Constraint
        # "Avoid that researchers have multiple visits with 3 or more researchers in one week"
        # Soft constraint: Penalty for each large visit beyond the first one.
        if settings.constraint_large_team_penalty:
            LARGE_TEAM_THRESHOLD = 3
            LARGE_TEAM_PENALTY = 60  # ~60 mins travel equivalent

            large_visits_vars = [
                x[i, j]
                for i in v_map
                if (i, j) in x
                and (getattr(v_map[i], "required_researchers", 1) or 1)
                >= LARGE_TEAM_THRESHOLD
            ]

            if large_visits_vars:
                large_count = model.NewIntVar(
                    0, len(large_visits_vars), f"large_count_{j}"
                )
                model.Add(large_count == sum(large_visits_vars))

                # Penalize max(0, count - 1)
                excess_large = model.NewIntVar(
                    0, len(large_visits_vars), f"excess_large_{j}"
                )
                model.Add(excess_large >= large_count - 1)
                # Implicitly excess_large >= 0 from domain

                # Since we maximize negative penalty, the solver will drive excess_large
                # to be the smallest possible value satisfying constraints, which is max(0, count-1).
                obj_terms.append(excess_large * -LARGE_TEAM_PENALTY)

    # 5. Coupling Preference (Supervision)
    # Rule: If visit has (Experience=Junior OR Contract=Flex) -> Must have (Experience=Senior OR (Contract=Intern AND Experience!=Junior))
    # Penalty if not satisfied. Only applies to multi-person visits.
    COUPLING_PENALTY = 30

    for i, v in v_map.items():
        if (getattr(v, "required_researchers", 1) or 1) <= 1:
            continue

        fam_name = (
            str(
                getattr(getattr(v, "species", [None])[0], "family", None)
                and getattr(getattr(v.species[0], "family", None), "name", "")
                or ""
            )
            .strip()
            .lower()
        )
        if fam_name != "vleermuis":
            continue

        # Identify assignments for visit i
        # Variables: x[i, j]
        assigned_user_indices = [j for j in u_map if (i, j) in x]
        if not assigned_user_indices:
            continue

        # Is Supervised (Junior or Flex)?
        supervised_vars = []
        supervisor_vars = []

        for j in assigned_user_indices:
            u = u_map[j]
            contract = str(getattr(u, "contract", "") or "")
            exp = str(getattr(u, "experience_bat", "") or "")

            is_supervised = exp == "Junior" or contract == "Flex"
            # Supervisor: Senior OR (Intern AND Not Junior)
            is_supervisor = exp in {"Senior", "Medior"} or (
                contract == "Intern" and exp != "Junior"
            )

            if is_supervised:
                supervised_vars.append(x[i, j])
            if is_supervisor:
                supervisor_vars.append(x[i, j])

        if supervised_vars:
            # Logic: exists_supervised AND NOT exists_supervisor -> Penalty

            has_supervised = model.NewBoolVar(f"has_supervised_{i}")
            model.Add(sum(supervised_vars) > 0).OnlyEnforceIf(has_supervised)
            model.Add(sum(supervised_vars) == 0).OnlyEnforceIf(has_supervised.Not())

            has_supervisor = model.NewBoolVar(f"has_supervisor_{i}")
            if supervisor_vars:
                model.Add(sum(supervisor_vars) > 0).OnlyEnforceIf(has_supervisor)
                model.Add(sum(supervisor_vars) == 0).OnlyEnforceIf(has_supervisor.Not())
            else:
                model.Add(has_supervisor == 0)

            # Violation = has_supervised AND NOT has_supervisor
            violation = model.NewBoolVar(f"coupling_violation_{i}")
            model.AddBoolAnd([has_supervised, has_supervisor.Not()]).OnlyEnforceIf(
                violation
            )
            model.AddBoolOr([has_supervised.Not(), has_supervisor]).OnlyEnforceIf(
                violation.Not()
            )

            obj_terms.append(violation * -COUPLING_PENALTY)

    # 6. Project Diversity
    # Preference: Avoid multiple visits to the same project for the same user in a week.
    # Penalty: 10 points per excess visit (count - 1).
    PROJECT_DIVERSITY_PENALTY = 10

    for j in u_map:
        # Group visit vars by project_id
        project_visits = {}  # pid -> list[var]

        for i, v in v_map.items():
            if (i, j) not in x:
                continue

            cluster = getattr(v, "cluster", None)
            pid = getattr(cluster, "project_id", None)

            if pid is not None:
                if pid not in project_visits:
                    project_visits[pid] = []
                project_visits[pid].append(x[i, j])

        for pid, p_vars in project_visits.items():
            if len(p_vars) <= 1:
                continue

            # If we potentially can assign multiple
            p_count = model.NewIntVar(0, len(p_vars), f"proj_count_{j}_{pid}")
            model.Add(p_count == sum(p_vars))

            p_excess = model.NewIntVar(0, len(p_vars), f"proj_excess_{j}_{pid}")
            model.Add(p_excess >= p_count - 1)
            # Implicit p_excess >= 0

            obj_terms.append(p_excess * -PROJECT_DIVERSITY_PENALTY)

    # 7. English/Dutch Teaming Constraint (Soft)
    # Rule: If a team has an English speaker (Language='EN'), it should ideally also have a Dutch speaker (Language='NL').
    # Penalty if not satisfied: (Has_EN AND NOT Has_NL) -> Penalty.
    # This applies to any visit. Single EN speaker is also penalized (needs buddy).

    if settings.constraint_english_dutch_teaming:
        LANGUAGE_TEAMING_PENALTY = 50

        for i, v in v_map.items():
            # Identify relevant user vars
            assigned_user_indices = [j for j in u_map if (i, j) in x]
            if not assigned_user_indices:
                continue

            en_vars = []
            nl_vars = []

            for j in assigned_user_indices:
                u = u_map[j]
                # Default to NL if not specified
                lang = str(getattr(u, "language", "NL") or "NL")

                if lang == "EN":
                    en_vars.append(x[i, j])
                elif lang == "NL":
                    nl_vars.append(x[i, j])

            if en_vars:
                # If there are English speakers, we check for Dutch speakers

                has_en = model.NewBoolVar(f"has_en_{i}")
                model.Add(sum(en_vars) > 0).OnlyEnforceIf(has_en)
                model.Add(sum(en_vars) == 0).OnlyEnforceIf(has_en.Not())

                has_nl = model.NewBoolVar(f"has_nl_{i}")
                if nl_vars:
                    model.Add(sum(nl_vars) > 0).OnlyEnforceIf(has_nl)
                    model.Add(sum(nl_vars) == 0).OnlyEnforceIf(has_nl.Not())
                else:
                    model.Add(has_nl == 0)

                # Violation: Has EN but NO NL
                violation = model.NewBoolVar(f"lang_violation_{i}")
                model.AddBoolAnd([has_en, has_nl.Not()]).OnlyEnforceIf(violation)
                model.AddBoolOr([has_en.Not(), has_nl]).OnlyEnforceIf(violation.Not())

                obj_terms.append(violation * -LANGUAGE_TEAMING_PENALTY)

    # 8. Daily Cluster Spread (feature_daily_planning only)
    # Preference: Avoid scheduling two visits to the same cluster on the same day
    # or consecutive days (prefer > 1 day gap between visits to the same cluster).
    # Penalty per "too close" visit pair (same or adjacent day).
    if settings.feature_daily_planning:
        DAILY_SPREAD_PENALTY = 25

        cluster_visit_indices: dict[int, list[int]] = {}
        for i, v in v_map.items():
            cid = getattr(v, "cluster_id", None)
            if cid is not None:
                cluster_visit_indices.setdefault(cid, []).append(i)

        for cid, v_indices in cluster_visit_indices.items():
            if len(v_indices) < 2:
                continue

            for k1 in range(len(v_indices)):
                for k2 in range(k1 + 1, len(v_indices)):
                    i1 = v_indices[k1]
                    i2 = v_indices[k2]

                    for d1 in range(5):
                        if (i1, d1) not in visit_day:
                            continue
                        for d2 in range(5):
                            if (i2, d2) not in visit_day:
                                continue
                            if abs(d1 - d2) > 1:
                                continue
                            # Both visits land on the same or adjacent day -> penalize
                            close_var = model.NewBoolVar(
                                f"cluster_close_{i1}_{i2}_{d1}_{d2}"
                            )
                            model.AddBoolAnd(
                                [visit_day[i1, d1], visit_day[i2, d2]]
                            ).OnlyEnforceIf(close_var)
                            model.AddBoolOr(
                                [visit_day[i1, d1].Not(), visit_day[i2, d2].Not()]
                            ).OnlyEnforceIf(close_var.Not())
                            obj_terms.append(close_var * -DAILY_SPREAD_PENALTY)

    # --- Heuristic Hint Injection ---

    # Generate greedy solution
    g_scheduled, g_day, g_assign = _generate_greedy_planning_solution(
        visits, users, user_caps, user_daypart_caps, week_monday
    )

    if _logger.isEnabledFor(logging.INFO):
        _logger.info(
            "GREEDY PLANNING: Scheduled %d/%d visits", len(g_scheduled), len(visits)
        )

    # Apply hints
    for i in v_map:
        # Scheduled status
        if i in g_scheduled:
            model.AddHint(scheduled[i], 1)

            # Day hint
            if i in g_day:
                d = g_day[i]
                model.AddHint(visit_day[i, d], 1)

            # Assignment hints
            if i in g_assign:
                for u_idx in g_assign[i]:
                    # map back to j
                    # We need to find j for this user.
                    # Users list is indexed 0..N, u_map is {j: u}.
                    # u_map keys match enumerate(users) index.
                    # Our greedy returns indices relative to the 'users' list passed in.
                    if (i, u_idx) in x:
                        model.AddHint(x[i, u_idx], 1)
        else:
            model.AddHint(scheduled[i], 0)

    model.Maximize(sum(obj_terms))

    # 3. Solve
    solver = cp_model.CpSolver()

    # Calculate timeout if not provided
    if timeout_seconds is None:
        # Dynamic Scaling:
        # Base floor 15s (was 30s).
        # Scale: N_visits * N_researchers * 0.005s
        # Max: 60s (was 120s).
        complexity = len(visits) * len(users)
        dynamic = complexity * 0.008
        timeout_seconds = max(5.0, min(45.0, dynamic))
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(
                "Computed solver timeout: %.2fs (Complexity=%d)",
                timeout_seconds,
                complexity,
            )

    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = 2

    # --- Pre-solve infeasibility diagnostics ---
    # Check known hard-constraint patterns that cause INFEASIBLE before the solver even runs.
    _pre_solve_diagnose(
        v_map=v_map,
        u_map=u_map,
        x=x,
        scheduled=scheduled,
        user_caps=user_caps,
        user_daypart_caps=user_daypart_caps,
        pre_blocked_slots=pre_blocked_slots,
        week_monday=week_monday,
        today=today,
    )

    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        scheduled_count = sum(1 for i in v_map if solver.Value(scheduled[i]))
        obj = solver.ObjectiveValue()
        bound = solver.BestObjectiveBound()
        denom = max(1.0, abs(bound))
        gap = max(0.0, (bound - obj) / denom)

        if status == cp_model.OPTIMAL:
            quality = "OPTIMAL"
        elif gap <= 0.01:
            quality = "EXCELLENT"
        elif gap <= 0.05:
            quality = "GOOD"
        elif gap <= 0.40:
            quality = "OK"
        else:
            quality = "WEAK"

        time_limit_reached = solver.WallTime() >= (timeout_seconds * 0.99)
        _logger.info(
            "WeeklyPlanning CP-SAT: status=%s time=%.2fs limit=%.1fs visits=%d users=%d scheduled=%d obj=%.2f bound=%.2f gap=%.4f conflicts=%d branches=%d",
            solver.StatusName(status),
            solver.WallTime(),
            timeout_seconds,
            len(visits),
            len(users),
            scheduled_count,
            obj,
            bound,
            gap,
            solver.NumConflicts(),
            solver.NumBranches(),
        )
        _logger.info(
            "WeeklyPlanning CP-SAT summary: quality=%s gap=%.4f time_limit_reached=%s",
            quality,
            gap,
            time_limit_reached,
        )

        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("=== DETAILED CANDIDATE SCORING ===")
            # Pre-calculate user total loads in this solution
            user_sol_loads = {}
            for j in u_map:
                user_sol_loads[j] = sum(
                    1 for vi in v_map if (vi, j) in x and solver.Value(x[vi, j])
                )

            for i, v in v_map.items():
                is_scheduled = solver.Value(scheduled[i])
                _logger.debug(
                    "Visit %s (Id=%s): Scheduled=%s",
                    i,
                    getattr(v, "id", "?"),
                    is_scheduled,
                )
                if not is_scheduled:
                    continue

                # Log candidates
                for j, u in u_map.items():
                    if (i, j) not in x:
                        continue

                    # Basic Stats
                    is_assigned = solver.Value(x[i, j])
                    tt = travel_costs.get((i, j), 0)
                    load = user_sol_loads.get(j, 0)

                    # Check Large Team Contribution (approx)
                    # We can't easily query the intermediate large_count var per user without more complex map,
                    # but we can re-calc:
                    # How many large visits is this user assigned to in this solution?
                    # "Large" definition matches the constraint logic earlier
                    large_visits_assigned = 0
                    for vi in v_map:
                        if (
                            (vi, j) in x
                            and solver.Value(x[vi, j])
                            and (getattr(v_map[vi], "required_researchers", 1) or 1)
                            >= 3
                        ):
                            large_visits_assigned += 1

                    _logger.debug(
                        "  -> Cand %s (Id=%s): Assigned=%s | Travel=%d min | TotalLoad=%d | LargeVisits=%d",
                        getattr(u, "full_name", "Unknown"),
                        getattr(u, "id", "?"),
                        "YES" if is_assigned else "no",
                        tt,
                        load,
                        large_visits_assigned,
                    )
    else:
        _logger.info(
            "WeeklyPlanning CP-SAT: status=%s time=%.2fs limit=%.1fs visits=%d users=%d conflicts=%d branches=%d",
            solver.StatusName(status),
            solver.WallTime(),
            timeout_seconds,
            len(visits),
            len(users),
            solver.NumConflicts(),
            solver.NumBranches(),
        )
        _logger.info("WeeklyPlanning CP-SAT summary: quality=FAILED")

        if status == cp_model.INFEASIBLE:
            # Log locked visits summary to help diagnose the conflict
            locked_visits = [
                (i, v) for i, v in v_map.items()
                if getattr(v, "researchers_locked", False) and getattr(v, "researchers", None)
            ]
            if locked_visits:
                _logger.warning(
                    "WeeklyPlanning INFEASIBLE: %d bezoek(en) met researchers_locked=True "
                    "(zie pre-solve diagnose hierboven voor details): %s",
                    len(locked_visits),
                    [getattr(v, "id", i) for i, v in locked_visits],
                )
            else:
                _logger.warning(
                    "WeeklyPlanning INFEASIBLE: geen researchers_locked bezoeken. "
                    "Mogelijke oorzaak: te weinig capaciteit voor verplichte combinaties "
                    "(strict availability, pre_blocked_slots, of gekwalificeerde onderzoekers)."
                )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        msg = (
            "WeeklyPlanning CP-SAT produced no feasible solution. "
            f"Status={solver.StatusName(status)}"
        )
        _logger.warning(msg)
        raise PlanningRunError(msg, technical_detail=msg)

    if scheduled_count == 0:
        msg = (
            "WeeklyPlanning CP-SAT scheduled 0 visits "
            f"(status={solver.StatusName(status)} gap={gap:.4f} limit={timeout_seconds:.1f}s time={solver.WallTime():.2f}s)"
        )
        _logger.warning(msg)
        raise PlanningRunError(msg, technical_detail=msg)

    planning_warning: str | None = None
    if quality == "WEAK":
        planning_warning = (
            "De automatische planning was moeilijk te optimaliseren. "
            "Controleer het resultaat zorgvuldig en pas eventueel handmatig aan."
        )
        _logger.warning(
            "WeeklyPlanning CP-SAT solution is WEAK but accepted: "
            "scheduled=%d gap=%.4f limit=%.1fs time=%.2fs",
            scheduled_count, gap, timeout_seconds, solver.WallTime(),
        )

    # 4. Extract Result
    selected_result = []

    # New: Tracking chosen dates
    day_assignments: dict[int, date] = {}
    from datetime import timedelta

    for i, v in v_map.items():
        if solver.Value(scheduled[i]):
            # Needs to be mutated? The caller expects visits with researchers assigned.
            # Yes, standard behavior: `v.researchers.append(...)`

            # Clear existing researchers (simulation safety)
            v.researchers = []

            # --- Extract Day ---
            chosen_day_idx = -1
            for d in range(5):
                if solver.Value(visit_day[i, d]):
                    chosen_day_idx = d
                    break

            if chosen_day_idx != -1:
                # Calculate actual date: week_monday + days
                actual_date = week_monday + timedelta(days=chosen_day_idx)
                if v.id is not None:
                    day_assignments[v.id] = actual_date

                # Also set on object for immediate use if needed (legacy compat remains planned_week)
                if get_settings().feature_daily_planning:
                    v.planned_date = actual_date

            assigned_users = []
            for j, u in u_map.items():
                if (i, j) in x and solver.Value(x[i, j]):
                    assigned_users.append(u)

            v.researchers.extend(assigned_users)

            # Note: We technically need to set planned_week too,
            # though caller might do it. Let's match legacy.
            v.planned_week = week

            selected_result.append(v)
        else:
            # Post-hoc reason analysis for visits the solver didn't schedule
            if v.id is not None and v.id not in skip_reason:
                allowed = _allowed_day_indices_for_visit(week_monday, v, today=today)
                if not allowed:
                    skip_reason[v.id] = "geen_dag_in_venster"
                elif not any((i, j) in x for j in u_map):
                    skip_reason[v.id] = "geen_gekwalificeerde_onderzoekers"
                elif getattr(v, "researchers_locked", False) and getattr(v, "researchers", None):
                    # Check if locked researchers are unqualified (not in x) vs. lacking capacity
                    locked_ids = {getattr(lu, "id", None) for lu in v.researchers} - {None}
                    locked_js = [j for j, u in u_map.items() if getattr(u, "id", None) in locked_ids]
                    locked_qualified = any((i, j) in x for j in locked_js)
                    if not locked_qualified:
                        skip_reason[v.id] = "onderzoekers_vergrendeld_niet_gekwalificeerd"
                    else:
                        skip_reason[v.id] = "onderzoekers_vergrendeld_geen_capaciteit"
                else:
                    skip_reason[v.id] = "capaciteitsgebrek"
            skipped_visits.append(v)

    # Remove Pool-2 (pairing-only) visits from skipped: they are not regular visits
    # and should not generate planning diagnostics when they end up unscheduled.
    skipped_visits = [v for v in skipped_visits if getattr(v, "id", None) not in _pairing_only_visit_ids]

    # 5. Build diagnostics
    diagnostics: list[WeeklyPlanningDiagnostic] = []
    for v in skipped_visits:
        vid = v.id
        if vid is None:
            continue
        reason_code = skip_reason.get(vid, "capaciteitsgebrek")
        reason_nl = _build_weekly_skip_reason_nl(v, reason_code, week_monday)
        diagnostics.append(
            WeeklyPlanningDiagnostic(
                visit_id=vid,
                reason_code=reason_code,
                reason_nl=reason_nl,
            )
        )

    return VisitSelectionResult(
        selected=selected_result,
        skipped=skipped_visits,
        remaining_caps={},  # Caller mostly ignores this for 'effective' logic
        day_assignments=day_assignments,
        diagnostics=diagnostics,
        planning_warning=planning_warning,
    )

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


class VisitSelectionResult(NamedTuple):
    selected: list[Visit]
    skipped: list[Visit]
    remaining_caps: dict[str, int]  # Global daypart caps (approximate)
    day_assignments: dict[int, date] | None = None  # visit_id -> date


def _generate_greedy_planning_solution(
    visits: list[Visit],
    users: list[User],
    user_caps: dict[int, int],
    user_daypart_caps: dict[int, dict[str, int]],
    week_monday: date,
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

        allowed_days = _allowed_day_indices_for_visit(week_monday, v)
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

    if (
        db and not isinstance(db, list) and not ignore_existing_assignments
    ):  # Hack: avoid calling valid db ops if it's a list (test mock)
        await _apply_existing_assignments_to_capacities(
            db, week, user_caps, user_daypart_caps
        )

    # Filter out visits with no daypart
    # AND enforce "Sequential Order": If multiple visits for same protocol are present,
    # keep only the one with the Lowest visit_index.

    from collections import defaultdict

    protocol_groups = defaultdict(list)

    clean_visits = []
    skipped_visits = []

    # 1. Group by Protocol
    for v in visits:
        pod = getattr(v, "part_of_day", None)
        if not pod or pod not in DAYPART_TO_AVAIL_FIELD:
            skipped_visits.append(v)
            continue

        # Check Protocol Windows
        pvws = getattr(v, "protocol_visit_windows", []) or []
        if not pvws:
            # If no protocol info, treat as independent
            clean_visits.append(v)
            continue

        for pvw in pvws:
            protocol_groups[pvw.protocol_id].append((pvw.visit_index, v))

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
    visits.sort(key=lambda v: _priority_key(week_monday, v))

    v_map = {i: v for i, v in enumerate(visits)}
    u_map = {i: u for i, u in enumerate(users)}

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

        def _full_addr(cluster) -> str | None:
            addr = getattr(cluster, "address", None)
            if not addr:
                return None
            addr = addr.strip()
            is_coords = bool(
                re.match(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$", addr)
                or re.match(r"^\d+°", addr)
            )
            if not is_coords:
                loc = getattr(getattr(cluster, "project", None), "location", None)
                if loc:
                    addr = f"{addr}, {loc}"
            return addr

        for i1, v1 in v_map.items():
            p1 = (getattr(v1, "part_of_day", None) or "").strip()
            addr1 = _full_addr(getattr(v1, "cluster", None))
            if not addr1 or not p1:
                continue
            for i2, v2 in v_map.items():
                if i1 == i2:
                    continue
                p2 = (getattr(v2, "part_of_day", None) or "").strip()
                if (p1, p2) not in _CONSEC_SAME_DAY and (p1, p2) != _OVERNIGHT_PAIR:
                    continue
                addr2 = _full_addr(getattr(v2, "cluster", None))
                if not addr2:
                    continue
                key = (addr1, addr2)
                _consec_pairs.append(key)
                _consec_pair_indices.setdefault(key, []).append((i1, i2))

        if _consec_pairs:
            consec_cluster_travel = await _tt_consec.get_travel_minutes_batch(
                _consec_pairs
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
    visit_weights = {i: BASE_REWARD + (len(visits) - i) * 100 for i in v_map}

    # --- Constraints ---

    for i, v in v_map.items():
        scheduled[i] = model.NewBoolVar(f"scheduled_{i}")

        # 2a. Visit Day Logic
        allowed_indices = _allowed_day_indices_for_visit(week_monday, v)
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
            model.Add(sum(days_vars) == 1).OnlyEnforceIf(scheduled[i])
            model.Add(sum(days_vars) == 0).OnlyEnforceIf(scheduled[i].Not())

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
                    model.Add(active_assignment[i, j, d] <= visit_day[i, d])
                    model.Add(
                        active_assignment[i, j, d] >= x[i, j] + visit_day[i, d] - 1
                    )
            else:
                pass

        # If scheduled, must assign exactly 'req' researchers
        if assigned_vars:
            model.Add(sum(assigned_vars) == req).OnlyEnforceIf(scheduled[i])
            model.Add(sum(assigned_vars) == 0).OnlyEnforceIf(scheduled[i].Not())
        else:
            model.Add(scheduled[i] == 0)

    # 2c. User Capacity Constraints

    for j, u in u_map.items():
        uid = getattr(u, "id", None)
        if uid is None:
            continue

        # Weekly Max
        cap_max = user_caps.get(uid, 0)
        user_assignments = [x.get((i, j)) for i in v_map if (i, j) in x]
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

            model.Add(sum(part_assignments) <= dedicated + fa)

        if total_flex_usage:
            model.Add(sum(total_flex_usage) <= flex_max)

    # 2d. Strict Day Coordination
    # In strict availability mode researchers may do 2 visits per day (double visits).
    max_visits_per_day = 2 if get_settings().feature_strict_availability else 1
    for j in u_map:
        for d in range(5):
            active_vars = [
                active_assignment[i, j, d]
                for i in v_map
                if (i, j, d) in active_assignment
            ]
            if active_vars:
                model.Add(sum(active_vars) <= max_visits_per_day)

    # 2e. Consecutive-daypart proximity constraint (strict availability mode only).
    # When a researcher is assigned two visits in consecutive dayparts — either on
    # the same day (Ochtend→Dag, Dag→Avond) or overnight (Avond on day D →
    # Ochtend on day D+1) — the clusters must be ≤30 minutes apart.  If the
    # pre-fetched travel time exceeds 30 minutes, forbid that combination.
    if get_settings().feature_strict_availability and consec_cluster_travel:

        def _full_addr_constraint(cluster) -> str | None:
            addr = getattr(cluster, "address", None)
            if not addr:
                return None
            addr = addr.strip()
            is_coords = bool(
                re.match(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$", addr)
                or re.match(r"^\d+°", addr)
            )
            if not is_coords:
                loc = getattr(getattr(cluster, "project", None), "location", None)
                if loc:
                    addr = f"{addr}, {loc}"
            return addr

        for i1, v1 in v_map.items():
            p1 = (getattr(v1, "part_of_day", None) or "").strip()
            addr1 = _full_addr_constraint(getattr(v1, "cluster", None))
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
                addr2 = _full_addr_constraint(getattr(v2, "cluster", None))
                if not addr2:
                    continue
                travel = consec_cluster_travel.get((addr1, addr2))
                if travel is None or travel <= 30:
                    continue
                # Travel time exceeds 30 min: forbid assigning the same researcher
                # to both visits in this consecutive order.
                for j in u_map:
                    if (i1, j) not in x or (i2, j) not in x:
                        continue
                    if is_same_day:
                        for d in range(5):
                            if (i1, j, d) in active_assignment and (
                                i2, j, d
                            ) in active_assignment:
                                model.Add(
                                    active_assignment[i1, j, d]
                                    + active_assignment[i2, j, d]
                                    <= 1
                                )
                    else:  # overnight: v1 is Avond on day d, v2 is Ochtend on day d+1
                        for d in range(4):
                            if (i1, j, d) in active_assignment and (
                                i2, j, d + 1
                            ) in active_assignment:
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

            for j, u in u_map.items():
                if _qualifies_user_for_visit(u, v):
                    origin = getattr(u, "address", None)
                    if not origin:
                        origin = getattr(u, "city", None)

                    if origin:
                        key = (origin, dest)
                        pairs_to_check.append(key)
                        if key not in pair_to_indices:
                            pair_to_indices[key] = []
                        pair_to_indices[key].append((i, j))

        # Parallel Fetch
        if pairs_to_check:
            batch_results = await travel_time.get_travel_minutes_batch(pairs_to_check)
            # Map back to indices
            for (origin, dest), mins in batch_results.items():
                indices_list = pair_to_indices.get((origin, dest), [])
                for i, j in indices_list:
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
                        model.Add(x[i, j] == 0)
                        continue
                    obj_terms.append(x[i, j] * -(cost * TRAVEL_TIME_WEIGHT))

    # Load Balancing Penalty (Quadratic)
    # For each user, sum of assignments^2

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
                large_count = model.NewIntVar(0, len(large_visits_vars), f"large_count_{j}")
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
        elif gap <= 0.15:
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

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        msg = (
            "WeeklyPlanning CP-SAT produced no feasible solution. "
            f"Status={solver.StatusName(status)}"
        )
        _logger.warning(msg)
        raise PlanningRunError(msg, technical_detail=msg)

    if quality == "WEAK" and time_limit_reached:
        msg = (
            "WeeklyPlanning CP-SAT solution rejected: quality=WEAK and time limit reached "
            f"(status={solver.StatusName(status)} gap={gap:.4f} limit={timeout_seconds:.1f}s time={solver.WallTime():.2f}s)"
        )
        _logger.warning(msg)
        raise PlanningRunError(msg, technical_detail=msg)

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
            skipped_visits.append(v)

    return VisitSelectionResult(
        selected=selected_result,
        skipped=skipped_visits,
        remaining_caps={},  # Caller mostly ignores this for 'effective' logic
        day_assignments=day_assignments,
    )

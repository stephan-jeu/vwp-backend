from __future__ import annotations

import logging
import re
from datetime import date
from typing import NamedTuple

from ortools.sat.python import cp_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.user import User

_logger = logging.getLogger("uvicorn.error")


class VisitSelectionResult(NamedTuple):
    selected: list[Visit]
    skipped: list[Visit]
    remaining_caps: dict[str, int]  # Global daypart caps (approximate)


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

        pref_uid = getattr(v, "preferred_researcher_id", None)

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
                is_preferred = pref_uid is not None and uid == pref_uid
                if not (is_preferred or _qualifies_user_for_visit(u, v)):
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

    Optimizes for:
    1. Maximizing total priority weight of scheduled visits.
    2. Preferring "Preferred Researchers".

    Constraints:
    - Weekly capacity per user.
    - Daypart capacity per user (Dedicated + Flex).
    - Qualification rules.
    - Strict day coordination: All researchers on a visit must go on the same valid day.
    - Visit valid day indices.
    """
    from app.services.visit_planning_selection import (
        _priority_key,
        _qualifies_user_for_visit,
        _eligible_visits_for_week,
        _allowed_day_indices_for_visit,
        _load_user_capacities,
        _load_user_daypart_capacities,
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
        pref_uid = getattr(v, "preferred_researcher_id", None)

        assigned_vars = []
        for j, u in u_map.items():
            # Check qualifications OR if user is preferred (bypass qualification)
            uid = getattr(u, "id", None)
            is_preferred = pref_uid is not None and uid is not None and uid == pref_uid

            qualified = _qualifies_user_for_visit(u, v)
            if is_preferred or qualified:
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
    for j in u_map:
        for d in range(5):
            active_vars = [
                active_assignment[i, j, d]
                for i in v_map
                if (i, j, d) in active_assignment
            ]
            if active_vars:
                model.Add(sum(active_vars) <= 1)

    # --- Objective ---
    obj_terms = []

    # Scale bonus relative to rank step (10)
    # 5 points bonus: prefers preferred researcher but not over a higher rank item?
    PREFERRED_BONUS = 5

    # Load Balancing Weight
    # Weight * (Delta Load^2) ~= Minutes of Travel
    # Weight=30 means:
    # 0->1 load (Delta 1^2 - 0^2 = 1) costs 30 points (equivalent to 30 mins travel)
    # 1->2 load (Delta 2^2 - 1^2 = 3) costs 90 points (marginal cost 60, +30 vs fresh user)
    LOAD_BALANCE_WEIGHT = 30

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
            pref_uid = getattr(v, "preferred_researcher_id", None)
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
                uid = getattr(u, "id", None)
                is_preferred = (
                    pref_uid is not None and uid is not None and uid == pref_uid
                )
                if is_preferred or _qualifies_user_for_visit(u, v):
                    origin = getattr(u, "address", None)
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

        pref_uid = getattr(v, "preferred_researcher_id", None)
        for j, u in u_map.items():
            if (i, j) in x:
                # Bonus for preferred
                uid = getattr(u, "id", None)
                is_preferred = (
                    pref_uid is not None and uid is not None and uid == pref_uid
                )
                if is_preferred:
                    obj_terms.append(x[i, j] * PREFERRED_BONUS)

                # Penalty for Travel Time
                cost = travel_costs.get((i, j), 0)
                if cost > 0:
                    obj_terms.append(x[i, j] * -cost)

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
    # Rule: If visit has (Experience=Nieuw OR Contract=Flex) -> Must have (Experience=Senior OR (Contract=Intern AND Experience!=Nieuw))
    # Penalty if not satisfied. Only applies to multi-person visits.
    COUPLING_PENALTY = 30

    for i, v in v_map.items():
        if (getattr(v, "required_researchers", 1) or 1) <= 1:
            continue

        # Identify assignments for visit i
        # Variables: x[i, j]
        assigned_user_indices = [j for j in u_map if (i, j) in x]
        if not assigned_user_indices:
            continue

        # Is Supervised (Nieuw or Flex)?
        supervised_vars = []
        supervisor_vars = []

        for j in assigned_user_indices:
            u = u_map[j]
            contract = str(getattr(u, "contract", "") or "")
            exp = str(getattr(u, "experience_bat", "") or "")

            is_supervised = exp == "Nieuw" or contract == "Flex"
            # Supervisor: Senior OR (Intern AND Not Nieuw)
            is_supervisor = exp == "Senior" or (contract == "Intern" and exp != "Nieuw")

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
        dynamic = complexity * 0.005
        timeout_seconds = max(15.0, min(60.0, dynamic))
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(
                "Computed solver timeout: %.2fs (Complexity=%d)",
                timeout_seconds,
                complexity,
            )

    solver.parameters.max_time_in_seconds = timeout_seconds
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        msg = f"CP-SAT Visit Selection failed. Status={solver.StatusName(status)}"
        _logger.warning(msg)
        return VisitSelectionResult(
            selected=[], skipped=visits + skipped_visits, remaining_caps={}
        )

    # 4. Extract Result
    selected_result = []

    # Calculate global remaining caps (approx) for consistency with return type
    # Though the caller relies mostly on selected list.

    for i, v in v_map.items():
        if solver.Value(scheduled[i]):
            # Needs to be mutated? The caller expects visits with researchers assigned.
            # Yes, standard behavior: `v.researchers.append(...)`

            # Clear existing researchers (simulation safety)
            v.researchers = []

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

    # Calculate global caps remaining?
    # Legacy `_select_visits_for_week_core` returned reduced caps.
    # But `select_visits_for_week` re-loads capacities anyway.
    # The return value `caps` from `_select_visits_for_week_core` was mainly used for logging
    # or the result tuple. We can return empty or basic calc.

    return VisitSelectionResult(
        selected=selected_result,
        skipped=skipped_visits,
        remaining_caps={},  # Caller mostly ignores this for 'effective' logic
    )

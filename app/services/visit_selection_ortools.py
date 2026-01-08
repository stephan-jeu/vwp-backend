from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import NamedTuple

from ortools.sat.python import cp_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.user import User
_logger = logging.getLogger("uvicorn.error")

class VisitSelectionResult(NamedTuple):
    selected: list[Visit]
    skipped: list[Visit]
    remaining_caps: dict[str, int] # Global daypart caps (approximate)

async def select_visits_cp_sat(
    db: AsyncSession, 
    week_monday: date,
    # Optional overrides for simulation
    visits: list[Visit] | None = None,
    users: list[User] | None = None,
    user_caps: dict[int, int] | None = None,
    user_daypart_caps: dict[int, dict[str, int]] | None = None
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
        _load_week_capacity,
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
        
    if db and not isinstance(db, list): # Hack: avoid calling valid db ops if it's a list (test mock)
        await _apply_existing_assignments_to_capacities(db, week, user_caps, user_daypart_caps)

    # Filter out visits with no daypart - they cannot be scheduled
    clean_visits = []
    skipped_visits = []
    for v in visits:
        pod = getattr(v, "part_of_day", None)
        if not pod or pod not in DAYPART_TO_AVAIL_FIELD:
             skipped_visits.append(v)
        else:
             clean_visits.append(v)
    visits = clean_visits
    
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
    u_id_map = {getattr(u, "id", None): i for i, u in enumerate(users) if getattr(u, "id", None) is not None}
    
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
            is_preferred = (pref_uid is not None and uid is not None and uid == pref_uid)
            
            qualified = _qualifies_user_for_visit(u, v)
            if is_preferred or qualified:
                x[i, j] = model.NewBoolVar(f"x_{i}_{j}")
                assigned_vars.append(x[i, j])
                
                # Active Assignment logic: x[i, j] AND visit_day[i, d]
                for d in range(5):
                     active_assignment[i, j, d] = model.NewBoolVar(f"active_{i}_{j}_{d}")
                     model.Add(active_assignment[i, j, d] <= x[i, j])
                     model.Add(active_assignment[i, j, d] <= visit_day[i, d])
                     model.Add(active_assignment[i, j, d] >= x[i, j] + visit_day[i, d] - 1)
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
        if uid is None: continue
        
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
                x[i, j] for i in v_map 
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
    
    # Helper to pre-calculate travel times for valid pairs
    # We only care about (i, j) pairs that are qualified/preferred
    pairs_to_check = []
    for i, v in v_map.items():
        pref_uid = getattr(v, "preferred_researcher_id", None)
        for j, u in u_map.items():
            uid = getattr(u, "id", None)
            is_preferred = (pref_uid is not None and uid is not None and uid == pref_uid)
            if is_preferred or _qualifies_user_for_visit(u, v):
                pairs_to_check.append((i, j))
    
    # Fetch travel times in batch/parallel if possible?
    # travel_time service is one-by-one.
    # We await them.
    travel_costs = {} 
    
    # Optimization: Check if we have travel_time service available (might be missing in tests if not mocked global?)
    # We imported it locally to be safe
    from app.services import travel_time
    
    for (i, j) in pairs_to_check:
        v = v_map[i]
        u = u_map[j]
        # Cluster address vs User address
        # Visit has cluster.address
        cluster = getattr(v, "cluster", None)
        dest = getattr(cluster, "address", None)
        origin = getattr(u, "address", None)
        
        cost = 0
        if origin and dest:
            # Default to 0 if lookup fails/returns None
            mins = await travel_time.get_travel_minutes(origin, dest)
            if mins is not None:
                cost = mins
        
        travel_costs[i, j] = cost

    for i, v in v_map.items():
        base_val = visit_weights[i]
        obj_terms.append(scheduled[i] * base_val)
        
        pref_uid = getattr(v, "preferred_researcher_id", None)
        for j, u in u_map.items():
             if (i, j) in x:
                 # Bonus for preferred
                 uid = getattr(u, "id", None)
                 is_preferred = (pref_uid is not None and uid is not None and uid == pref_uid)
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
        
        load_sq = model.NewIntVar(0, len(visits)**2, f"load_sq_{j}")
        model.AddMultiplicationEquality(load_sq, [load_var, load_var])
        
        # Load Balancing Weighted by Percentage Utilization
        # Previous: load_sq * -LOAD_BALANCE_WEIGHT
        # New: load_sq * - (LOAD_BALANCE_WEIGHT * 5 / Capacity)
        
        cap_max = user_caps.get(getattr(u, "id", None) or 0, 5) # Default to 5 if unknown
        if cap_max < 1: cap_max = 1
        
        weighted_penalty = int(LOAD_BALANCE_WEIGHT * 5 / cap_max)
        
        obj_terms.append(load_sq * -weighted_penalty)
        
        # 4. Large Team Visit Constraint
        # "Avoid that researchers have multiple visits with 3 or more researchers in one week"
        # Soft constraint: Penalty for each large visit beyond the first one.
        LARGE_TEAM_THRESHOLD = 3
        LARGE_TEAM_PENALTY = 60 #~60 mins travel equivalent
        
        large_visits_vars = [
            x[i, j] for i in v_map 
            if (i, j) in x and (getattr(v_map[i], "required_researchers", 1) or 1) >= LARGE_TEAM_THRESHOLD
        ]
        
        if large_visits_vars:
            large_count = model.NewIntVar(0, len(large_visits_vars), f"large_count_{j}")
            model.Add(large_count == sum(large_visits_vars))
            
            # Penalize max(0, count - 1)
            excess_large = model.NewIntVar(0, len(large_visits_vars), f"excess_large_{j}")
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
            
            is_supervised = (exp == "Nieuw" or contract == "Flex")
            # Supervisor: Senior OR (Intern AND Not Nieuw)
            is_supervisor = (exp == "Senior" or (contract == "Intern" and exp != "Nieuw"))
            
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
            model.AddBoolAnd([has_supervised, has_supervisor.Not()]).OnlyEnforceIf(violation)
            model.AddBoolOr([has_supervised.Not(), has_supervisor]).OnlyEnforceIf(violation.Not())
            
            
            obj_terms.append(violation * -COUPLING_PENALTY)
            
    # 6. Project Diversity
    # Preference: Avoid multiple visits to the same project for the same user in a week.
    # Penalty: 10 points per excess visit (count - 1).
    PROJECT_DIVERSITY_PENALTY = 10
    
    for j in u_map:
        # Group visit vars by project_id
        project_visits = {} # pid -> list[var]
        
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

    model.Maximize(sum(obj_terms))
    
    # 3. Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 1.0 # Fast interactive response
    status = solver.Solve(model)
    
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _logger.warning("CP-SAT Visit Selection failed to find solution")
        return VisitSelectionResult(selected=[], skipped=visits + skipped_visits, remaining_caps={})

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
        remaining_caps={} # Caller mostly ignores this for 'effective' logic
    )

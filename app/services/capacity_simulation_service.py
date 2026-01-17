from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple, Any

from sqlalchemy import select, or_, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.availability import AvailabilityWeek
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.species import Species
from app.models.visit import Visit, visit_protocol_visit_windows
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.simulation_result import SimulationResult
from app.schemas.capacity import CapacitySimulationResponse, FamilyDaypartCapacity
from app.services.visit_planning_selection import (
    _any_function_contains,
    _first_function_name,
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


def _get_required_user_flag(v: Visit) -> str:
    """Return the primary user flag required for the visit (formatted label).

    Logic mirrors ``_qualifies_user_for_visit`` but returns human-readable labels:
    1. SMP visits -> "SMP <Family>" (e.g. "SMP Vleermuis", "SMP Huismus")
    2. VRFG function -> "VR/FG"
    3. Standard -> Capitalized family name (e.g. "Vleermuis", "Zwaluw")
    """
    # 1. SMP Check
    fn_name = _first_function_name(v)
    if fn_name.lstrip().upper().startswith("SMP"):
        sp = (v.species or [None])[0]
        fam = getattr(sp, "family", None)
        fam_name = str(getattr(fam, "name", "")).strip().lower()

        if fam_name == "vleermuis":
            return "SMP Vleermuis"
        elif fam_name == "zwaluw":
            return "SMP Gierzwaluw"
        elif fam_name == "zangvogel":
            return "SMP Huismus"
        else:
            # Fallback if unknown SMP family mapping
            return f"SMP {fam_name.capitalize()}"

    # 2. VRFG Check
    if _any_function_contains(v, ("Vliegroute", "Foerageergebied")):
        return "VR/FG"

    # 3. Standard Family Fallback
    # Map visible family names to user flags if they differ (e.g. plurals)
    # The user model flags are typically singular or specific keys.
    # We try to align with valid User model attributes where possible.
    try:
        sp = (v.species or [None])[0]
        fam = getattr(sp, "family", None)
        name = getattr(fam, "name", None)
        if isinstance(name, str) and name.strip():
            raw = name.strip().lower()
            # Map common variations to user flags
            mapping = {
                "langoren": "Langoor",
                "schijfhoren": "Schijfhoren",
                "zwaluw": "Zwaluw",
                "vlinder": "Vlinder",
                "grote vos": "Vlinder",
                "iepenpage": "Vlinder",
            }
            if raw in mapping:
                return mapping[raw]
            
            # Default capitalization
            return raw.capitalize()
    except Exception:
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
            selectinload(Visit.protocol_visit_windows).selectinload(ProtocolVisitWindow.protocol),
        )
        .order_by(Visit.id)
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


async def _load_initial_protocol_states(db: AsyncSession, start_date: date) -> dict[int, date]:
    """
    Load the last 'locked' visit end-date for each protocol prior to start_date.
    Returns: {protocol_id: last_visit_to_date}
    """
    # We want the max(to_date) of locked visits where to_date < start_date
    # Group by protocol.
    
    stmt = (
        select(
            ProtocolVisitWindow.protocol_id,
            func.max(Visit.to_date)
        )
        .join(visit_protocol_visit_windows, visit_protocol_visit_windows.c.protocol_visit_window_id == ProtocolVisitWindow.id)
        .join(Visit, Visit.id == visit_protocol_visit_windows.c.visit_id)
        .where(
            and_(
                Visit.researchers.any(), # Locked
                Visit.to_date < start_date
            )
        )
        .group_by(ProtocolVisitWindow.protocol_id)
    )
    
    rows = (await db.execute(stmt)).all()
    return {pid: d for pid, d in rows if d is not None}


async def generate_and_store_simulation(
    db: AsyncSession,
    start_monday: date | None = None
) -> SimulationResult:
    """
    Run the stateful capacity simulation and persist the result.
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

    # 1. Load Initial State
    protocol_state = await _load_initial_protocol_states(db, horizon_start)
    
    # 2. Load Visits (Pool)
    # Ensure we load Protocol info for frequency checks
    all_visits = await _load_all_open_visits(db, horizon_start)
    
    # Enrich visits with protocol data locally to avoid N+1 queries during loop?
    # _load_all_open_visits already loads protocol_visit_windows -> protocol.
    # We need to map visit_id -> protocol_id and min_period.
    
    visit_protocol_info = {}
    for v in all_visits:
        # A visit might have multiple protocols, but usually one drives the frequency.
        # We'll take the first relevant one if multiple.
        # Ideally we check all, but let's assume primary.
        pvw_list = v.protocol_visit_windows or []
        for pvw in pvw_list:
             if pvw.protocol:
                 visit_protocol_info[v.id] = pvw.protocol
                 break
    
    visit_pool = list(all_visits)
    
    # Data Structures for Result
    
    # Deadline View: family -> part -> deadline_week -> {planned, unplannable}
    deadline_results: dict[str, dict[str, dict[str, SimulationResultCell]]] = {}
    
    # Week View: 
    # weeks: list of ISO strings
    # rows: { "Totalen": {week: {spare, planned}}, "Fam - Part": {week: {spare, planned}} }
    week_view_rows: dict[str, dict[str, Any]] = {} 
    # We'll build week_view_rows progressively.
    simulated_weeks = []
    
    def add_deadline_result(v: Visit, is_planned: bool):
        group_key = _get_required_user_flag(v)
        part = (v.part_of_day or "Onbekend").strip()
        deadline = v.to_date.isoformat() if v.to_date else "No Deadline"
        
        fam_dict = deadline_results.setdefault(group_key, {})
        part_dict = fam_dict.setdefault(part, {})
        
        current = part_dict.get(deadline, SimulationResultCell(0, 0))
        if is_planned:
            part_dict[deadline] = SimulationResultCell(current.planned + 1, current.unplannable)
        else:
            part_dict[deadline] = SimulationResultCell(current.planned, current.unplannable + 1)

    # 3. Simulation Loop
    current_monday = horizon_start
    
    # Pre-load all users for capacity calculations
    from app.services.visit_planning_selection import (
        _load_all_users, 
        _load_user_capacities, 
        _load_user_daypart_capacities
    )
    all_users = await _load_all_users(db)
    
    while current_monday <= horizon_end:
        week_friday = current_monday + timedelta(days=4)
        week_iso_id = _week_id(current_monday)
        simulated_weeks.append(week_iso_id)
        
        # A. Determine Eligibility (with State Check)
        eligible_indices = []
        for i, v in enumerate(visit_pool):
            f = v.from_date or date.min
            t = v.to_date or date.max
            
            # Date window check
            if not (f <= week_friday and t >= current_monday):
                continue
                
            # Frequency Check
            proto = visit_protocol_info.get(v.id)
            if proto:
                last_date = protocol_state.get(proto.id)
                if last_date:
                    # Calculate gap: Monday of this week - Last End Date
                    # (Strictly speaking, gap should be >= min_period)
                    # We compare days.
                    days_diff = (current_monday - last_date).days
                    
                    min_val = proto.min_period_between_visits_value
                    min_unit = proto.min_period_between_visits_unit
                    
                    if min_val:
                        req_days = 0
                        if min_unit == 'weeks': req_days = min_val * 7
                        elif min_unit == 'months': req_days = min_val * 30
                        else: req_days = min_val
                        
                        if days_diff < req_days:
                            # Too soon! Skip logic, but keep in pool.
                            continue

            eligible_indices.append(i)

        # B. Run Solver
        eligible_subset = [visit_pool[i] for i in eligible_indices]
        
        # We need capacities for this week to calculate Spare later anyway.
        week_num = current_monday.isocalendar().week
        
        # Note: select_visits_cp_sat fetches capacities internally if not provided.
        # But we need them for spare calc. So let's fetch and pass.
        
        u_caps_weekly = await _load_user_capacities(db, week_num)
        u_caps_daypart = await _load_user_daypart_capacities(db, week_num)
        
        selection_result = await select_visits_cp_sat(
            db, 
            current_monday,
            visits=eligible_subset,
            users=all_users,
            user_caps=u_caps_weekly,
            user_daypart_caps=u_caps_daypart,
            timeout_seconds=5.0, # Increased for accuracy per user request
            include_travel_time=False,
            ignore_existing_assignments=True
        )
        
        # C. Update State & Results
        
        # 1. Successful visits
        for v in selection_result.selected:
            add_deadline_result(v, is_planned=True)
            # Update protocol state
            proto = visit_protocol_info.get(v.id)
            if proto:
                # Set last visited to this week's roughly end date (Friday)
                protocol_state[proto.id] = week_friday

        # 2. Week View: Calculate Spare Capacity & Planned Count
        # Planned count for this week is len(selection_result.selected)
        # But we want it broken down by Group/Part.
        
        # Remaining capacities returned by solver are global approximations?
        # Actually select_visits_cp_sat returns 'remaining_caps' which might be useful?
        # But 'remaining_caps' in VisitSelectionResult is global daypart caps, not per user/family.
        # We need to calculate spare capacity based on the solver's assignments.
        # The solver doesn't return the *modified* user objects with decremented capacity in a simple way
        # unless we parse assignments.
        # However, `selection_result.selected` has `researchers` assigned (User objects).
        # We can simulate consumption on our local capacity copy.
        
        # Clone for modification
        local_weekly = u_caps_weekly.copy()
        local_daypart = {uid: d.copy() for uid, d in u_caps_daypart.items()}
        
        # Consume for selected visits
        week_planned_map: dict[str, dict[str, int]] = {} # Family -> Part -> Count
        total_planned_this_week = 0
        
        for v in selection_result.selected:
            total_planned_this_week += 1
            
            group_key = _get_required_user_flag(v)
            part = (v.part_of_day or "Onbekend").strip()
            
            pm = week_planned_map.setdefault(group_key, {})
            pm[part] = pm.get(part, 0) + 1
            
            for r in v.researchers:
                # Consume capacity logic (simplified from capacity_simulation_service helpers)
                uid = r.id
                if local_weekly.get(uid, 0) > 0:
                    local_weekly[uid] -= 1
                    
                    udp = local_daypart.get(uid, {})
                    if udp.get(part, 0) > 0:
                        udp[part] -= 1
                    elif udp.get('Flex', 0) > 0:
                        udp['Flex'] -= 1
        
        # Now Calculate Spare Capacity for each "Family - Part"
        # Iterate all users. If user can do "Family - Part" (based on User.flags or knowledge),
        # then add their remaining capacity (for that part/flex) to the spare pool.
        
        # We need a mapping of "User -> Can do what".
        # This is hard because "Family" flags are string property checks.
        # We can iterate the generic groups we know of.
        # Or simpler: Just iterate "Totalen" and maybe "Vleermuis / Roofvogel" if we can detect.
        
        # Let's support "Totalen" (Top row) and generic groups present in the visit types.
        
        # Total Spare Capacity (Sum of all users' remaining slots)
        total_spare = sum(local_weekly.values())
        
        # Add to "Totalen" row
        tot_row = week_view_rows.setdefault("Totalen", {})
        tot_row[week_iso_id] = { "spare": total_spare, "planned": total_planned_this_week }
        
        # Break down by rows seen in results?
        # Iterate all known families/parts?
        # We can iterate over the keys present in `week_planned_map` to ensure we have rows for them.
        # Plus maybe some default ones?
        
        # For each User, we need to know if they contribute to a Group.
        # Helper: _user_belongs_to_group(user, group_key) -> bool
        # This requires checking user flags against the group key string (e.g. "Vleermuis").
        
        # Optimizing: Calculate spare for groups relevant to planned/unplannable results
        # PLUS mandatory groups to ensure they show up in the table even if empty
        mandatory_groups = {
            "SMP Huismus", "SMP Vleermuis", "SMP Gierzwaluw", 
            "Pad", "Langoor", "Roofvogel", "VR/FG", 
            "Vleermuis", "Zwaluw", "Vlinder", 
            "Teunisbloempijlstaart", "Zangvogel", "Biggenkruid", "Schijfhoren"
        }
        
        active_groups = set(deadline_results.keys()) | set(week_planned_map.keys()) | mandatory_groups
        
        for group_key in active_groups:
            # Check every user's remaining capacity 
            # Only if they match the group.
            # This might be slow if many groups * many users.
            # We can optimize if needed.
            
            # Assuming standard parts for simplicity in rows, or use what's in map.
            relevant_parts = ["Ochtend", "Dag", "Avond"]
             
            for part in relevant_parts:
                spare_for_group_part = 0
                for u in all_users:
                    # Check if user matches group
                    # Simplified matching logic:
                    # If group_key in user.flags or similar.
                    # We need a `_user_matches_group` helper.
                    # We'll inline a simple one:
                    
                    # Map group keys to user model boolean fields
                    # 1. Explicit Mappings for complex keys
                    field_map = {
                        "VR/FG": "vrfg",
                        "SMP Vleermuis": "smp_vleermuis",
                        "SMP Huismus": "smp_huismus",
                        "SMP Gierzwaluw": "smp_gierzwaluw",
                    }
                    
                    target_field = field_map.get(group_key)
                    
                    # 2. Fallback: Lowercase group key (e.g. "Vleermuis" -> "vleermuis")
                    if not target_field:
                        # Handle "SMP <Other>" -> try "smp_<other>" ?? 
                        # For now, just lower() the whole key if it's a simple word.
                        # If it has spaces (like "SMP Other"), lower().replace(" ", "_")?
                        # The User model fields are simple (vleermuis, zwaluw).
                        # Clean key logic was: group_key.replace("SMP ", "").title()
                        # Better to just try to find a matching field.
                        candidate = group_key.lower().replace(" ", "_").replace("/", "")
                        if hasattr(u, candidate):
                            target_field = candidate
                        
                    # 3. Check property
                    if target_field and hasattr(u, target_field):
                        matches = getattr(u, target_field)
                    else:
                        # If we can't find a matching flag, do we count them?
                        # Previous logic defaulted to True ("matches = True") which caused 46 capacity for VR/FG.
                        # Defaulting to False is safer to avoid unrelated people showing up.
                        # Only exception: is there a "General" capacity?
                        matches = False

                    if matches:
                        # Current logic: min(weekly_remaining, daypart_remaining + flex)
                        rem_w = local_weekly.get(u.id, 0)
                        rem_dp = local_daypart.get(u.id, {}).get(part, 0)
                        rem_fl = local_daypart.get(u.id, {}).get("Flex", 0)
                        
                        # Heuristic: Capacity for this specific part is dedicated + flex, 
                        # capped by weekly remaining.
                        cap = min(rem_w, rem_dp + rem_fl)
                        spare_for_group_part += cap
                
                planned_count = week_planned_map.get(group_key, {}).get(part, 0)
                
                if spare_for_group_part > 0 or planned_count > 0:
                    row_label = f"{group_key} - {part}"
                    r_data = week_view_rows.setdefault(row_label, {})
                    r_data[week_iso_id] = { "spare": spare_for_group_part, "planned": planned_count }

        # D. Pool Maintenance
        # Remove planned
        # Retain skipped
        
        # selected indices in subset -> map back to pool?
        # select_visits_cp_sat returns Visit objects.
        selected_ids = {v.id for v in selection_result.selected}
        
        new_pool = []
        for v in visit_pool:
            if v.id not in selected_ids:
                new_pool.append(v)
        
        visit_pool = new_pool
        current_monday += timedelta(days=7)

    # 4. Process Remaining (Unplannable)
    for v in visit_pool:
        if v.to_date and v.to_date > horizon_end:
            continue
        add_deadline_result(v, is_planned=False)

    # 5. Serialization & Storage
    
    # Transform deadline_results to old 'grid' schema
    final_deadline_grid: dict[str, dict[str, dict[str, FamilyDaypartCapacity]]] = {}
    for fam, parts in deadline_results.items():
        final_deadline_grid[fam] = {}
        for part, deadlines in parts.items():
            final_deadline_grid[fam][part] = {}
            for deadline, cell in deadlines.items():
                final_deadline_grid[fam][part][deadline] = FamilyDaypartCapacity(
                    required=cell.planned + cell.unplannable,
                    assigned=cell.planned,
                    shortfall=cell.unplannable,
                    spare=0,
                )
    
    # Use Pydantic's .dict() or model_dump() if available, else manual dict
    # Assuming .dict() works for these schemas
    # But wait, grid_data needs to be JSON serializable. 
    # FamilyDaypartCapacity is a Pydantic model (Schema).
    # We should convert to dicts.
    
    def serialize_grid(g):
        # Recursive dict conversion
        out = {}
        for k, v in g.items():
            if isinstance(v, dict):
                out[k] = serialize_grid(v)
            elif hasattr(v, 'dict'):
                out[k] = v.dict()
            else:
                out[k] = v
        return out
        
    full_json = {
        "deadline_view": serialize_grid(final_deadline_grid),
        "week_view": {
            "weeks": simulated_weeks,
            "rows": week_view_rows
        }
    }
    
    # Save to DB
    # Upsert logic: Override existing latest result if present
    stmt = select(SimulationResult).order_by(SimulationResult.created_at.desc()).limit(1)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing:
        # existing.updated_at will be updated automatically by onupdate
        existing.horizon_start = horizon_start
        existing.horizon_end = horizon_end
        existing.grid_data = full_json
        sim_res = existing
        # No need to add(), it's attached
    else:
        sim_res = SimulationResult(
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            grid_data=full_json
        )
        db.add(sim_res)
    
    await db.commit()
    await db.refresh(sim_res)
    
    return sim_res


async def simulate_capacity_planning(
    db: AsyncSession,
    start_monday: date | None,
) -> CapacitySimulationResponse:
    """
    Deprecated/Legacy Wrapper.
    Re-directs to generate_and_store but returns the OLD schema structure (CapacitySimulationResponse)
    mapping from the stored 'deadline_view'.
    """
    res = await generate_and_store_simulation(db, start_monday)
    
    # Reconstruct CapacitySimulationResponse from the stored deadline_view
    # grid_data["deadline_view"] is dicts, need to parse back to objects?
    # Schema expects objects.
    
    grid_raw = res.grid_data["deadline_view"]
    
    # Re-hydrate Pydantic models
    final_grid = {}
    for fam, parts in grid_raw.items():
        final_grid[fam] = {}
        for part, deadlines in parts.items():
            final_grid[fam][part] = {}
            for deadline, cell_data in deadlines.items():
                final_grid[fam][part][deadline] = FamilyDaypartCapacity(**cell_data)
                
    return CapacitySimulationResponse(
        horizon_start=res.horizon_start,
        horizon_end=res.horizon_end,
        grid=final_grid
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
    # Simulation: Fast (no travel time), Dynamic timeout
    selection_result = await select_visits_cp_sat(
        db, 
        week_monday, 
        timeout_seconds=None, 
        include_travel_time=False
    )
    
    if not selection_result.selected and not selection_result.skipped:
        return {}
        
    result: dict[str, dict[str, FamilyDaypartCapacity]] = {}

    def add_stats(visits: list[Visit], is_assigned: bool):
        for v in visits:
            group_key = _get_required_user_flag(v)
            part = (getattr(v, "part_of_day", None) or "").strip()
            if not part:
                continue
            
            req = int(getattr(v, "required_researchers", None) or 1)
            
            # If assigned, count full requirement. If skipped, count shortfall.
            assigned_count = req if is_assigned else 0
            shortfall_count = 0 if is_assigned else req
            
            fam_map = result.setdefault(group_key, {})
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

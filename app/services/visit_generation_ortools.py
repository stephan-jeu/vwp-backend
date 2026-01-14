from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import date, timedelta

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.protocol import Protocol
from app.models.visit import Visit
from app.services.visit_generation_common import (
    _generate_visit_requests,
    _build_compatibility_graph,
    _derive_part_options_base,
    _select_most_restrictive_precipitation,
    calculate_visit_props,
)

_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}
_logger = logging.getLogger("uvicorn.error")



def _get_june_ordinals(year: int) -> list[int]:
    """Return ordinals for June 1st to June 30th."""
    return [date(year, 6, d).toordinal() for d in range(1, 31)]

def _get_july_ordinals(year: int) -> list[int]:
    """Return ordinals for July 1st to July 31st."""
    return [date(year, 7, d).toordinal() for d in range(1, 32)]

def _get_maternity_ordinals(year: int) -> list[int]:
    """Return ordinals for Maternity period (Assume 15 May - 15 July)."""
    start = date(year, 5, 15)
    end = date(year, 7, 15)
    delta = (end - start).days
    delta = (end - start).days
    return [(start + timedelta(days=i)).toordinal() for i in range(delta + 1)]


def _generate_greedy_solution(requests: list) -> dict[int, int]:
    """
    Generate a simple First-Fit greedy assignment of requests to visits.
    Returns: dict {request_index: visit_index}
    """
    # Sort requests to potentially improve packing (e.g. most constrained first?)
    # For now, just process in order or by ID.
    # Sorting by number of compatibility constraints (degree) might be better, 
    # but simple First Fit is usually surprising good as a baseline.
    
    # Map visit_index -> list of assigned request indices
    bins: dict[int, list[int]] = {}
    assignment: dict[int, int] = {}
    
    for r_idx, r in enumerate(requests):
        placed = False
        
        # Try to fit in existing bins
        for v_idx, existing_r_idxs in bins.items():
            # Check compatibility with ALL requests currently in this bin
            compatible_with_all = True
            for existing_idx in existing_r_idxs:
                existing_req = requests[existing_idx]
                # Check if r is compatible with existing_req
                # Note: 'compatible_request_ids' contains IDs of requests compatible with 'r'
                if existing_req.id not in r.compatible_request_ids:
                    compatible_with_all = False
                    break
            
            if compatible_with_all:
                bins[v_idx].append(r_idx)
                assignment[r_idx] = v_idx
                placed = True
                break
        
        if not placed:
            # Create new bin
            new_v_idx = len(bins) 
            bins[new_v_idx] = [r_idx]
            assignment[r_idx] = new_v_idx
            
    return assignment


async def generate_visits_cp_sat(
    db: AsyncSession,
    cluster: Cluster,
    protocols: list[Protocol],
    *,
    default_required_researchers: int | None = None,
    default_preferred_researcher_id: int | None = None,
    default_expertise_level: str | None = None,
    default_wbc: bool = False,
    default_fiets: bool = False,
    default_hub: bool = False,
    default_dvp: bool = False,
    default_sleutel: bool = False,
    default_remarks_field: str | None = None,
) -> tuple[list[Visit], list[str]]:
    """Generate visits for a cluster using Google OR-Tools CP-SAT Solver.
    
    This solver allows global optimization of visit scheduling, correcting legacy issues
    where local greedy decisions led to suboptimal or invalid schedules.
    """
    if not protocols:
        return [], []

    warnings: list[str] = []

    if _DEBUG_VISIT_GEN:
        _logger.info("Starting CP-SAT Visit Gen for Cluster %s", cluster.id)

    # 1. Request Generation
    requests = _generate_visit_requests(protocols)
    if not requests:
        return [], warnings

    # Post-process requests to restore flexibility lost in standard generation
    # `_generate_visit_requests` applies strict pruning based on legacy logic.
    # We revert to base options here to let the solver decide globally.
    for r in requests:
        p = r.protocol
        
        # User Rule: ABSOLUTE_TIME strictly implies 'Avond'
        if p.start_timing_reference == "ABSOLUTE_TIME":
            r.part_of_day_options = {"Avond"}
            continue

        # Exception: Force 'Avond' for RD Paarverblijf Visit 1 to support 00:00 start time.
        if (
            r.visit_index == 1
            and getattr(p.function, "name", "") == "Paarverblijf"
            and getattr(p.species, "abbreviation", "") == "RD"
        ):
            r.part_of_day_options = {"Avond"}
            continue

        req_morning = getattr(p, "requires_morning_visit", False)
        req_evening = getattr(p, "requires_evening_visit", False)
        
        # If strict requirement flags are present, re-derive base options to allow maximum flexibility.
        # This allows the solver to satisfy "At Least One" global constraints without pre-splitting.
        if req_morning or req_evening:
             base = _derive_part_options_base(p)
             r.part_of_day_options = base

    # Build compatibility graph (populates r.compatible_request_ids)
    _build_compatibility_graph(requests)

    if _DEBUG_VISIT_GEN:
        _logger.info("GRAPH: Generated %d requests", len(requests))

    # 2. Model Construction
    model = cp_model.CpModel()
    max_visits = len(requests)

    # --- Heuristic Hint Injection ---
    # To avoid "FEASIBLE" but poor solutions (e.g. 1 visit per request), we calculate 
    # a greedy First-Fit solution and provide it as a hint to the solver.
    # This helps the solver start from a "Reasonable" neighborhood.
    
    greedy_assignment = _generate_greedy_solution(requests)
    
    if _DEBUG_VISIT_GEN:
        used_visits = len(set(greedy_assignment.values()))
        _logger.info("GREEDY: Found initial solution with %d visits (Hinting Solver)", used_visits)
    # --------------------------------

    # Variables
    visit_active = [model.NewBoolVar(f"visit_active_{v}") for v in range(max_visits)]
    
    req_to_visit = {}
    for r_idx, req in enumerate(requests):
        for v in range(max_visits):
            var = model.NewBoolVar(f"r{r_idx}_in_v{v}")
            req_to_visit[(r_idx, v)] = var
            
            # Apply Hint
            if greedy_assignment.get(r_idx) == v:
                model.AddHint(var, 1)
            else:
                model.AddHint(var, 0)
    
    # Hint visit_active status based on greedy assignment
    active_visit_indices = set(greedy_assignment.values())
    for v in range(max_visits):
        if v in active_visit_indices:
             model.AddHint(visit_active[v], 1)
        else:
             model.AddHint(visit_active[v], 0)
            
    min_date_ord = min(r.window_from.toordinal() for r in requests)
    max_date_ord = max(r.window_to.toordinal() for r in requests)
    
    visit_start = [model.NewIntVar(min_date_ord, max_date_ord, f"visit_start_{v}") for v in range(max_visits)]
    visit_part = [model.NewIntVar(0, 2, f"visit_part_{v}") for v in range(max_visits)] # 0=Ochtend, 1=Dag, 2=Avond
    req_start = [model.NewIntVar(min_date_ord, max_date_ord, f"req_start_{r_idx}") for r_idx in range(len(requests))]

    # C1. Every request must be assigned to EXACTLY one visit
    for r_idx, _ in enumerate(requests):
        model.Add(sum(req_to_visit[(r_idx, v)] for v in range(max_visits)) == 1)
        
    # C2. Visit Activation: If any request is in visit v, visit v is active
    for v in range(max_visits):
        model.AddMaxEquality(visit_active[v], [req_to_visit[(r_idx, v)] for r_idx in range(len(requests))])
        
    # C3. Symmetry Breaking (Sort visits by active status to push empty visits to end)
    for v in range(max_visits - 1):
        model.Add(visit_active[v] >= visit_active[v+1])
        
    # C4. Validity Constraints per Request
    part_map = {"Ochtend": 0, "Dag": 1, "Avond": 2}
    req_parts = [] # Keep track of assigned part for req (for global check)

    for r_idx, req in enumerate(requests):
        # Channeling: link req_start to visit_start
        for v in range(max_visits):
            model.Add(req_start[r_idx] == visit_start[v]).OnlyEnforceIf(req_to_visit[(r_idx, v)])

        # Window Constraints
        model.Add(req_start[r_idx] >= req.window_from.toordinal())
        model.Add(req_start[r_idx] <= req.window_to.toordinal())
        
        # Compatibility Constraints
        for r2_idx in range(r_idx + 1, len(requests)):
            r2 = requests[r2_idx]
            if r2.id not in req.compatible_request_ids:
                 for v in range(max_visits):
                     model.AddBoolOr([req_to_visit[(r_idx, v)].Not(), req_to_visit[(r2_idx, v)].Not()])

        # Predecessor / Gap Constraints
        if req.predecessor:
            pred_id, gap_days = req.predecessor
            # Find pred index by ID scan
            pred_idx = next((i for i, r in enumerate(requests) if r.id == pred_id), None)
            if pred_idx is not None:
                model.Add(req_start[r_idx] >= req_start[pred_idx] + gap_days)
        
        # Part of Day Variable for Request
        allowed_parts = req.part_of_day_options
        domain_vals = []
        if allowed_parts:
            domain_vals = sorted([part_map[p] for p in allowed_parts if p in part_map])
        else:
            domain_vals = [0, 1, 2] # All
            
        rp = model.NewIntVarFromDomain(cp_model.Domain.FromValues(domain_vals), f"req_part_{r_idx}")
        req_parts.append(rp)
        
        # Channeling: visit_part must match req_part if assigned
        for v in range(max_visits):
             model.Add(visit_part[v] == rp).OnlyEnforceIf(req_to_visit[(r_idx, v)])

    # C6. "At Least One" Global Constraints
    requests_by_proto = defaultdict(list)
    for r_idx, req in enumerate(requests):
        requests_by_proto[req.protocol.id].append(r_idx)
        
    for p_id, r_idxs in requests_by_proto.items():
        p = requests[r_idxs[0]].protocol
        
        req_morning = getattr(p, "requires_morning_visit", False)
        req_evening = getattr(p, "requires_evening_visit", False)
        
        if req_morning:
            # At least one visit must be Morning
            bools = []
            for rx in r_idxs:
                b = model.NewBoolVar(f"p{p_id}_r{rx}_is_morning")
                model.Add(req_parts[rx] == 0).OnlyEnforceIf(b)
                model.Add(req_parts[rx] != 0).OnlyEnforceIf(b.Not())
                bools.append(b)
            model.Add(sum(bools) >= 1)

        if req_evening:
            # At least one visit must be Evening
            bools = []
            for rx in r_idxs:
                b = model.NewBoolVar(f"p{p_id}_r{rx}_is_evening")
                model.Add(req_parts[rx] == 2).OnlyEnforceIf(b)
                model.Add(req_parts[rx] != 2).OnlyEnforceIf(b.Not())
                bools.append(b)
            model.Add(sum(bools) >= 1)
            
        # Month/Period Constraints (June, July, Maternity)
        req_june = getattr(p, "requires_june_visit", False)
        req_july = getattr(p, "requires_july_visit", False)
        req_maternity = getattr(p, "requires_maternity_period_visit", False)
        
        if req_june or req_july or req_maternity:
             # Assume year from first window
             year = date.fromordinal(min_date_ord).year
             
             for condition, valid_ords_func in [
                 (req_june, _get_june_ordinals), 
                 (req_july, _get_july_ordinals), 
                 (req_maternity, _get_maternity_ordinals)
             ]:
                 if condition:
                     valid_ords = set(valid_ords_func(year))
                     domain_obj = cp_model.Domain.FromValues(sorted(list(valid_ords)))
                     
                     bools = []
                     for rx in r_idxs:
                         b = model.NewBoolVar(f"p{p_id}_r{rx}_cond")
                         model.AddLinearExpressionInDomain(req_start[rx], domain_obj).OnlyEnforceIf(b)
                         bools.append(b)
                     model.Add(sum(bools) >= 1)

    # C7. Penalize "Tight" Windows (Short Effective Duration)
    # User discourages planning resulting in effective windows < 7 days.
    # We apply a penalty if (visit_end - visit_start) < 7 days, forcing the solver to prefer
    # adding another visit over squeezing protocols into a tight window.
    
    visit_end = [model.NewIntVar(min_date_ord, max_date_ord + 365, f"visit_end_{v}") for v in range(max_visits)]
    is_short = [model.NewBoolVar(f"visit_is_short_{v}") for v in range(max_visits)]
    
    infinity_ord = max_date_ord + 100 
    
    for v in range(max_visits):
        # Determine effective end date of the visit as the minimum of assigned requests' window_to.
        # If visit is inactive (no requests), the value defaults to infinity_ord.
        ends_in_visit = []
        for r_idx, req in enumerate(requests):
            eff = model.NewIntVar(min_date_ord, infinity_ord, f"eff_end_r{r_idx}_v{v}")
            model.Add(eff == req.window_to.toordinal()).OnlyEnforceIf(req_to_visit[(r_idx, v)])
            model.Add(eff == infinity_ord).OnlyEnforceIf(req_to_visit[(r_idx, v)].Not())
            ends_in_visit.append(eff)
        
        model.AddMinEquality(visit_end[v], ends_in_visit)
        
        # Check Shortness: If active AND duration < 7, set is_short=1
        model.Add(is_short[v] == 0).OnlyEnforceIf(visit_active[v].Not())
        
        duration = model.NewIntVar(-365, 3650, f"duration_{v}")
        model.Add(duration == visit_end[v] - visit_start[v])
        
        model.Add(duration < 7).OnlyEnforceIf([visit_active[v], is_short[v]])
        model.Add(duration >= 7).OnlyEnforceIf([visit_active[v], is_short[v].Not()])

    # Objective Function
    M = (max_date_ord - min_date_ord) * len(requests) * 2 + 1000
    SHORT_PENALTY = M + 500 # Cost higher than adding a new visit (M)
    
    # Priority:
    # 1. Minimize total Visits (M)
    # 2. Avoid Short Windows (SHORT_PENALTY)
    # 3. Prefer Morning Requests (Weight 2)
    # 4. Compactness / Early Starts (Weight 1)
    # 5. Prefer Morning Visits (Tie-break weight 1)
    
    model.Minimize(
        sum(visit_active[v] * M for v in range(max_visits)) + 
        sum(is_short[v] * SHORT_PENALTY for v in range(max_visits)) +
        sum(rp * 2 for rp in req_parts) + 
        sum(req_start) + 
        sum(visit_part) 
    )

    # Solve
    solver = cp_model.CpSolver()
    
    # Dynamic Time Limit: Scale with complexity (number of requests)
    # Base 30s + 0.5s per request. For 75 requests -> ~50s. For 500 -> 250s.
    # We can be more aggressive now that we have the Greedy Hint to prevent disaster cases.
    time_limit = max(30.0, len(requests) * 0.5)
    solver.parameters.max_time_in_seconds = time_limit
    
    # Enable parallelism to avoid getting stuck in a single search tree.
    # We force 8 workers even on single-core machines to enable "Portfolio Search".
    # This runs different search strategies (randomization, core-based, etc.) in time-sliced threads,
    # significantly reducing the chance of hitting a worst-case exponential runtime.
    solver.parameters.num_search_workers = 8
    
    if _DEBUG_VISIT_GEN:
        _logger.info("Solver Time Limit set to %.1fs for %d requests", time_limit, len(requests))

    status = solver.Solve(model)
    
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        msg = f"CP-SAT Infeasible. Status={solver.StatusName(status)}"
        _logger.warning(msg)
        return [], [msg]

    if _DEBUG_VISIT_GEN:
        _logger.info("CP-SAT Solved: Status=%s Val=%s", solver.StatusName(status), solver.ObjectiveValue())

    # Reconstruct Visits
    visits: list[Visit] = []
    inv_part_map = {0: "Ochtend", 1: "Dag", 2: "Avond"}

    for v in range(max_visits):
        if not solver.BooleanValue(visit_active[v]):
            continue
            
        start_ord = solver.Value(visit_start[v])
        part_idx = solver.Value(visit_part[v])
        visit_date = date.fromordinal(start_ord)
        part_str = inv_part_map.get(part_idx)
        
        assigned_req_indices = [i for i in range(len(requests)) if solver.BooleanValue(req_to_visit[(i, v)])]
        assigned_reqs = [requests[i] for i in assigned_req_indices]
        
        # Extend the effective "window" to the minimum end date of all assigned requests.
        min_window_to = min(req.window_to for req in assigned_reqs)
        final_to_date = min_window_to
        
        # Create Visit
        new_visit = Visit(
            from_date=visit_date,
            to_date=final_to_date, 
            part_of_day=part_str,
            cluster_id=cluster.id,
        )

        # Apply defaults
        new_visit.required_researchers = default_required_researchers
        new_visit.preferred_researcher_id = default_preferred_researcher_id
        new_visit.expertise_level = default_expertise_level
        new_visit.wbc = default_wbc
        new_visit.fiets = default_fiets
        new_visit.hub = default_hub
        new_visit.dvp = default_dvp
        new_visit.sleutel = default_sleutel
        
        # Attach protocols and related entities
        unique_protos = list({r.protocol.id: r.protocol for r in assigned_reqs}.values())
        new_visit.protocols = unique_protos
        new_visit.functions = list({p.function.id: p.function for p in unique_protos if p.function}.values())
        new_visit.species = list({p.species.id: p.species for p in unique_protos if p.species}.values())
        
        # Calculate duration/text
        try:
             ref_date = min(r.window_from for r in assigned_reqs) if assigned_reqs else visit_date
             v_indices = {r.protocol.id: r.visit_index for r in assigned_reqs}
             
             dur, txt = calculate_visit_props(unique_protos, part_str, reference_date=ref_date, visit_indices=v_indices)
             new_visit.duration = dur
             new_visit.start_time_text = txt
        except ImportError:
             pass

        # Weather Constraints
        min_temp = max(
            (p.min_temperature_celsius for p in unique_protos if p.min_temperature_celsius is not None),
            default=None
        )
        max_wind = min(
            (p.max_wind_force_bft for p in unique_protos if p.max_wind_force_bft is not None),
            default=None
        )
        precip_options = [p.max_precipitation for p in unique_protos if p.max_precipitation]
        precip = _select_most_restrictive_precipitation(precip_options)
        
        new_visit.min_temperature_celsius = min_temp
        new_visit.max_wind_force_bft = max_wind
        new_visit.max_precipitation = precip

         # Generate Remarks Field
        remarks_lines = []
        fn_map = defaultdict(lambda: defaultdict(set))
        
        active_pairs = set()
        visit_indices = set()
        
        for r in assigned_reqs:
             p = r.protocol
             fn_name = getattr(getattr(p, "function", None), "name", None)
             sp_abbr = getattr(getattr(p, "species", None), "abbreviation", None) or getattr(getattr(p, "species", None), "name", None)
             if fn_name and sp_abbr:
                 active_pairs.add((fn_name, sp_abbr))
                 fn_map[fn_name][sp_abbr].add(r.visit_index)
                 visit_indices.add(r.visit_index)

        all_fns = {f for f, s in active_pairs}
        all_sps = {s for f, s in active_pairs}
        cartesian_product = {(f, s) for f in all_fns for s in all_sps}
        
        # Optimize remarks: suppress if all combinations are present and indices are uniform
        is_full_product = (active_pairs == cartesian_product)
        is_uniform_indices = (len(visit_indices) == 1)
        
        if not (is_full_product and is_uniform_indices):
            for fn in sorted(fn_map.keys()):
                 entries = []
                 for sp, idxs in sorted(fn_map[fn].items()):
                     idx_str = "/".join(str(i) for i in sorted(idxs))
                     entries.append(f"{sp} ({idx_str})")
                 if entries:
                     remarks_lines.append(f"{fn}: {', '.join(entries)}")

        # Special Case: Rugstreeppad using specific function
        has_rugstreeppad_platen = False
        for r in assigned_reqs:
            p = r.protocol
            s_name = getattr(getattr(p, "species", None), "name", "")
            f_name = getattr(getattr(p, "function", None), "name", "")
            if s_name == "Rugstreeppad" and f_name == "platen neerleggen, eisnoeren/larven":
                has_rugstreeppad_platen = True
                break
        
        if has_rugstreeppad_platen:
            remarks_lines.append("Fijnmazig schepnet (RAVON-type) mee. Ook letten op koren en aanwezige individuen. Platen neerleggen in plangebied. Vuistregel circa 10 platen per 100m geschikt leefgebied.")
            
        # Special Case: Vlinder Family
        has_vlinder = False
        for r in assigned_reqs:
             p = r.protocol
             fam_name = getattr(getattr(getattr(p, "species", None), "family", None), "name", "")
             if fam_name == "Vlinder":
                 has_vlinder = True
                 break
        
        if has_vlinder:
            remarks_lines.append("Min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (met meer >50% bewolking)")
            
        # Special Case: Langoren Family
        has_langoren = False
        for r in assigned_reqs:
             p = r.protocol
             fam_name = getattr(getattr(getattr(p, "species", None), "family", None), "name", "")
             if fam_name == "Langoren":
                 has_langoren = True
                 break
        
        if has_langoren:
            remarks_lines.append("Geen mist, sneeuwval. Bodemtemperatuur < 15 graden")
            
        # Special Case: SMP Zwaluw
        has_smp_zwaluw = False
        for r in assigned_reqs:
             p = r.protocol
             fam_name = getattr(getattr(getattr(p, "species", None), "family", None), "name", "")
             func_name = getattr(getattr(p, "function", None), "name", "") or ""
             if fam_name == "Zwaluw" and func_name.startswith("SMP"):
                 has_smp_zwaluw = True
                 break
        
        if has_smp_zwaluw:
            remarks_lines.append("""Minimum temperatuur:
25 Mei - 31 Mei: 17
1 Jun - 7 Jun: 18
8 Jun - 14 Jun: 19
15 Jun - 21 Jun: 19.5
22 Jun - 28 Jun: 20
29 Jun - 5 Jul: 20
6 Jul - 12 Jul: 20
13 Jul - 19 Jul: 20""")
            
        if remarks_lines:
             new_visit.remarks_field = "\n".join(remarks_lines)
        
        if default_remarks_field:
            if new_visit.remarks_field:
                new_visit.remarks_field += "\n" + default_remarks_field
            else:
                new_visit.remarks_field = default_remarks_field
        
        # Calculate Series Start Date (tie-breaker for sorting)
        series_starts = []
        for p in unique_protos:
            if p.visit_windows:
                series_starts.append(min(w.window_from for w in p.visit_windows))
        
        new_visit._sort_series_start = min(series_starts) if series_starts else date.max

        visits.append(new_visit)
        
    # Final Sort and Numbering
    # Final Sort and Numbering
    # --------------------------
    # To fix restart-from-1 issue when adding visits, we fetch ALL existing visits for this cluster.
    
    # 1. Fetch existing visits
    stmt = select(Visit).where(Visit.cluster_id == cluster.id)
    result = await db.execute(stmt)
    existing_visits = result.scalars().all()
    
    # 2. Combine with new visits (which are not yet in DB, but objects exist)
    all_cluster_visits = list(existing_visits) + visits
    
    # 3. Sort Chronologically
    # Primary: Date
    # Secondary: Series Start (computed for new, None/AttributeError for old?)
    # Tertiary: Part of day
    # Tie-break: ID (stable for old), random/memory for new.
    
    def sort_key(x: Visit):
        d = x.from_date or date.max
        # For existing visits, _sort_series_start won't be set. Use date as fallback.
        s_start = getattr(x, "_sort_series_start", d)
        pod_map = {"Ochtend": 0, "Dag": 1, "Avond": 2}
        pod = pod_map.get(x.part_of_day, 3)
        return (d, s_start, pod)

    all_cluster_visits.sort(key=sort_key)
    
    # 4. Re-Apply Numbering
    for i, v in enumerate(all_cluster_visits):
        v.visit_nr = i + 1
        # If it's an existing visit, we need to ensure it's added to session for update?
        # Typically selecting it attaches it to session. 
        # But if we modified it (visit_nr changed), we should ensure it's tracked.
        db.add(v)
        
        if _DEBUG_VISIT_GEN and i >= len(existing_visits): # Log new ones
             _logger.info("  -> Created Visit %d: %s %s (%s)", v.visit_nr, v.from_date, v.part_of_day, v.remarks_field)

    return visits, warnings

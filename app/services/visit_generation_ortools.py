from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cluster import Cluster
from app.models.protocol import Protocol
from app.models.visit import Visit
from app.services.visit_generation_graph import (
    VisitRequest,
    _build_compatibility_graph,
    _derive_part_options_base,
    _generate_visit_requests,
    _select_most_restrictive_precipitation,
    _to_current_year,
)

_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}
_logger = logging.getLogger("uvicorn.error")

MIN_EFFECTIVE_WINDOW_DAYS = int(os.getenv("MIN_EFFECTIVE_WINDOW_DAYS", "10"))
SOLVER_TIME_LIMIT_SECONDS = 5.0

def _get_june_ordinals(year: int) -> list[int]:
    """Return ordinals for June 1st to June 30th."""
    start = date(year, 6, 1)
    return [date(year, 6, d).toordinal() for d in range(1, 31)]

def _get_july_ordinals(year: int) -> list[int]:
    """Return ordinals for July 1st to July 31st."""
    return [date(year, 7, d).toordinal() for d in range(1, 32)]

def _get_maternity_ordinals(year: int) -> list[int]:
    """Return ordinals for Maternity period (Assume 15 May - 15 July)."""
    start = date(year, 5, 15)
    end = date(year, 7, 15)
    delta = (end - start).days
    return [(start + timedelta(days=i)).toordinal() for i in range(delta + 1)]


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

    Implementation V2: Corrected "At Least One" Logic.
    Instead of pre-filtering requests based on morning/evening flags (which splits visits),
    we allow the solver to choose freely, but enforce GLOBAL constraints that
    at least one visit per protocol must satisfy the required condition.
    """
    if not protocols:
        return [], []

    warnings: list[str] = []

    if _DEBUG_VISIT_GEN:
        _logger.info("Starting CP-SAT Visit Gen (V2) for Cluster %s", cluster.id)

    # 1. Request Generation
    # We use the graph generation helper, but we must undo its strict pruning.
    requests = _generate_visit_requests(protocols)
    if not requests:
        return [], warnings

    # RE-PROCESS REQUESTS TO RESTORE FLEXIBILITY
    # The helper `_generate_visit_requests` applies pruning based on logic.
    # We want to revert to `base_parts` if a flag is responsible for the pruning.
    for r in requests:
        p = r.protocol
        
        # FIX: Handle ABSOLUTE_TIME as strictly "Avond" (User Request)
        # "ABSOLUTE_TIME takes precedence over SUNSET"
        if p.start_timing_reference == "ABSOLUTE_TIME":
            r.part_of_day_options = {"Avond"}
            continue

        # EXCEPTION: RD Paarverblijf Visit 1 -> Force Avond (for Midnight start)
        # We override any existing options to ensure it falls in the night/evening bucket.
        if (
            r.visit_index == 1
            and getattr(p.function, "name", "") == "Paarverblijf"
            and getattr(p.species, "abbreviation", "") == "RD"
        ):
            r.part_of_day_options = {"Avond"}
            # Continue to skip standard logic? Yes, we want to force this.
            continue

        req_morning = getattr(p, "requires_morning_visit", False)
        req_evening = getattr(p, "requires_evening_visit", False)
        
        # If strict requirement flags are present, we might have been pre-pruned.
        # We re-derive base options to allow maximum flexibility for the solver.
        if req_morning or req_evening:
             base = _derive_part_options_base(p)
             # Update the request to use base options
             # This allows e.g. "Avond" and "Ochtend" both to be valid choices,
             # letting the solver pick "Ochtend" for V1 and "Avond" for V2 to satisfy global constraints.
             r.part_of_day_options = base

    # Build compatibility graph
    _build_compatibility_graph(requests)

    if _DEBUG_VISIT_GEN:
        _logger.info("GRAPH: Generated %d requests", len(requests))
        for r in requests:
            p = r.protocol
            fam = getattr(getattr(p.species, "family", None), "name", "?")
            sp = getattr(p.species, "abbreviation", "?")
            fn = getattr(p.function, "name", "?")
            _logger.info(
                "  Req %s: [%s] %s - %s (Visit %d) Window=%s->%s Parts=%s",
                r.id, fam, sp, fn, r.visit_index, r.window_from, r.window_to, r.part_of_day_options
            )

    # 2. Model Construction
    model = cp_model.CpModel()
    max_visits = len(requests)
    
    # Variables
    visit_active = [model.NewBoolVar(f"visit_active_{v}") for v in range(max_visits)]
    
    req_to_visit = {}
    for r_idx, req in enumerate(requests):
        for v in range(max_visits):
            req_to_visit[(r_idx, v)] = model.NewBoolVar(f"r{r_idx}_in_v{v}")
            
    min_date_ord = min(r.window_from.toordinal() for r in requests)
    max_date_ord = max(r.window_to.toordinal() for r in requests)
    
    visit_start = [model.NewIntVar(min_date_ord, max_date_ord, f"visit_start_{v}") for v in range(max_visits)]
    visit_part = [model.NewIntVar(0, 2, f"visit_part_{v}") for v in range(max_visits)] # 0=Ochtend, 1=Dag, 2=Avond
    req_start = [model.NewIntVar(min_date_ord, max_date_ord, f"req_start_{r_idx}") for r_idx in range(len(requests))]

    # C1. Every request must be assigned to EXACTLY one visit
    for r_idx, range_req in enumerate(requests): # Using range_req as dummy, iterating index
        model.Add(sum(req_to_visit[(r_idx, v)] for v in range(max_visits)) == 1)
        
    # C2. Visit Activation: If any request is in visit v, visit v is active
    for v in range(max_visits):
        model.AddMaxEquality(visit_active[v], [req_to_visit[(r_idx, v)] for r_idx in range(len(requests))])
        
    # C3. Symmetry Breaking
    for v in range(max_visits - 1):
        model.Add(visit_active[v] >= visit_active[v+1])
        
    # C4. Validity Constraints per Request
    part_map = {"Ochtend": 0, "Dag": 1, "Avond": 2} # Map string to int
    
    req_parts = [] # Keep track of assigned part for req (for global check)

    for r_idx, req in enumerate(requests):
        # Channeling: link req_start to visit_start
        for v in range(max_visits):
            model.Add(req_start[r_idx] == visit_start[v]).OnlyEnforceIf(req_to_visit[(r_idx, v)])

        # Window Constraints
        model.Add(req_start[r_idx] >= req.window_from.toordinal())
        model.Add(req_start[r_idx] <= req.window_to.toordinal())
        
        # Compatibility (Pre-computed)
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
            # sum(is_morning[r]) >= 1
            bools = []
            for rx in r_idxs:
                b = model.NewBoolVar(f"p{p_id}_r{rx}_is_morning")
                model.Add(req_parts[rx] == 0).OnlyEnforceIf(b)
                model.Add(req_parts[rx] != 0).OnlyEnforceIf(b.Not())
                bools.append(b)
            model.Add(sum(bools) >= 1)

        if req_evening:
            # sum(is_evening[r]) >= 1
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
                     # Ensure we handle year boundaries if needed (simple assumption: single season per run)
                     domain_obj = cp_model.Domain.FromValues(sorted(list(valid_ords)))
                     
                     bools = []
                     for rx in r_idxs:
                         b = model.NewBoolVar(f"p{p_id}_r{rx}_cond")
                         # b => req_start in domain
                         # Note: OnlyEnforceIf works on LinearConstraint.
                         # Need intermediate variable or LinearExprInDomain? 
                         # CP-SAT allows: model.AddLinearExpressionInDomain(expr, domain).OnlyEnforceIf(bool)
                         model.AddLinearExpressionInDomain(req_start[rx], domain_obj).OnlyEnforceIf(b)
                         bools.append(b)
                     model.Add(sum(bools) >= 1)

    # C7. Penalize "Tight" Windows (Short Effective Duration)
    # User dislikes visits with effective window < 7 days ("Tight Planning").
    # We define `visit_end[v]` as the MIN of window_to of all requests in v.
    # If (visit_end - visit_start) < 7, we apply a penalty > Cost of new visit (M).
    # This forces the solver to split/rearrange (adding a visit) rather than squeeze.
    
    visit_end = [model.NewIntVar(min_date_ord, max_date_ord + 365, f"visit_end_{v}") for v in range(max_visits)]
    is_short = [model.NewBoolVar(f"visit_is_short_{v}") for v in range(max_visits)]
    
    # Large constant for inactive requests in min calculation
    infinity_ord = max_date_ord + 100 
    
    for v in range(max_visits):
        # Gather effective ends for this visit
        # If r is in v: eff_end = r.window_to
        # If r NOT in v: eff_end = infinity
        ends_in_visit = []
        for r_idx, req in enumerate(requests):
            eff = model.NewIntVar(min_date_ord, infinity_ord, f"eff_end_r{r_idx}_v{v}")
            # r assigned to v => eff = window_to
            model.Add(eff == req.window_to.toordinal()).OnlyEnforceIf(req_to_visit[(r_idx, v)])
            # r NOT assigned => eff = infinity
            model.Add(eff == infinity_ord).OnlyEnforceIf(req_to_visit[(r_idx, v)].Not())
            ends_in_visit.append(eff)
        
        # visit_end[v] = min(assigned window_to's)
        # If visit is empty, min is infinity. But visit_active constraint handles empty case (inactive).
        # We need to constrain visit_end only if active, or rely on min?
        # AddMinEquality returns min of all. If all are infinity, result is infinity.
        # We cap visit_end at max_date_ord normally, but here we allow it to go high to indicate "empty"?
        # Actually, simpler: define visit_end domain up to infinity.
        model.AddMinEquality(visit_end[v], ends_in_visit)
        
        # Check Shortness: Duration < 7 ?
        # Duration = visit_end - visit_start
        # Only check if visit is active. If inactive, is_short = False.
        # Constraint: is_short <=> (visit_end - visit_start < 7) AND visit_active
        
        # Impl: 
        # 1. If not active => not short
        model.Add(is_short[v] == 0).OnlyEnforceIf(visit_active[v].Not())
        
        # 2. If active: 
        # is_short=1 => duration < 7
        # is_short=0 => duration >= 7
        duration = model.NewIntVar(-365, 3650, f"duration_{v}") # allow neg temp
        model.Add(duration == visit_end[v] - visit_start[v])
        
        # logic
        model.Add(duration < 7).OnlyEnforceIf([visit_active[v], is_short[v]])
        model.Add(duration >= 7).OnlyEnforceIf([visit_active[v], is_short[v].Not()])

    # Objective
    M = (max_date_ord - min_date_ord) * len(requests) * 2 + 1000
    SHORT_PENALTY = M + 500 # Cost higher than adding a new visit
    
    # Weights:
    # 1. Minimize Visits (Primary) -> M
    # 2. Avoid Short Windows -> SHORT_PENALTY
    # 3. Prefer Morning Requests -> Weight 2 per unit (Avond=2 => Cost 4). 
    #    Cost 4 is equivalent to 4 days delay.
    # 4. Compactness (Early Starts) -> Weight 1
    # 5. Prefer Morning Visits (Tie-break) -> Weight 1
    
    model.Minimize(
        sum(visit_active[v] * M for v in range(max_visits)) + 
        sum(is_short[v] * SHORT_PENALTY for v in range(max_visits)) +
        sum(rp * 2 for rp in req_parts) + # Prioritize Requests in Morning
        sum(req_start) + # Compactness
        sum(visit_part)  # Tie-break: Prefer Morning(0)
    )

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    status = solver.Solve(model)
    
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        msg = f"CP-SAT Infeasible. Status={solver.StatusName(status)}"
        _logger.warning(msg)
        return [], [msg]

    if _DEBUG_VISIT_GEN:
        _logger.info("CP-SAT Solved: Status=%s Val=%s", solver.StatusName(status), solver.ObjectiveValue())

    # Reconstruct
    visits: list[Visit] = []
    inv_part_map = {0: "Ochtend", 1: "Dag", 2: "Avond"}

    for v in range(max_visits):
        if not solver.BooleanValue(visit_active[v]):
            continue
            
        start_ord = solver.Value(visit_start[v])
        part_idx = solver.Value(visit_part[v])
        visit_date = date.fromordinal(start_ord)
        part_str = inv_part_map.get(part_idx)
        
        # Identify assigned protocols
        assigned_req_indices = [i for i in range(len(requests)) if solver.BooleanValue(req_to_visit[(i, v)])]
        assigned_reqs = [requests[i] for i in assigned_req_indices]
        
        # To-Date Logic: Restore Window Behavior
        # The solver picks a specific start date (valid >= max(window_from)).
        # We can extend the "window" to the minimum end date of all assigned requests.
        # This preserves the flexibility shown in the graph algorithm.
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
        
        # Attach transient relations
        unique_protos = list({r.protocol.id: r.protocol for r in assigned_reqs}.values())
        new_visit.protocols = unique_protos
        new_visit.functions = list({p.function.id: p.function for p in unique_protos if p.function}.values())
        new_visit.species = list({p.species.id: p.species for p in unique_protos if p.species}.values())
        
        # Calculate duration/text
        from .visit_generation import calculate_visit_props
        try:
             # Use minimum window start as reference date for month-based logic
             ref_date = min(r.window_from for r in assigned_reqs) if assigned_reqs else visit_date
             
             # Build visit_indices map for exceptions (e.g. RD V1)
             v_indices = {r.protocol.id: r.visit_index for r in assigned_reqs}
             
             dur, txt = calculate_visit_props(unique_protos, part_str, reference_date=ref_date, visit_indices=v_indices)
             new_visit.duration = dur
             new_visit.start_time_text = txt
        except ImportError:
             pass

        # Weather Constraints (Ported from Graph Logic)
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

         # Build remarks field (Legacy logic replication)
        remarks_lines = []
        fn_map = defaultdict(lambda: defaultdict(set))
        
        # New Optimization: Suppress remarks if redundancy check passes & all indices match
        # Logic: If (Functions x Species) == ActiveProtocols, and indices are uniform?
        # User said: "Besides the visit index info...".
        # But if we suppress text, we lose index info.
        # User implies index info is less valuable than clarity or is standard.
        # Let's check strict Cartesian Product of (Function Name, Species Abbr).
        
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
        
        
        # Check 1: Is the active set equal to the full Cartesian product?
        is_full_product = (active_pairs == cartesian_product)
        
        # Check 2: Are all visit indices uniform? (e.g. all (1) or all (2))
        is_uniform_indices = (len(visit_indices) == 1)
        
        if not (is_full_product and is_uniform_indices):
            for fn in sorted(fn_map.keys()):
                 entries = []
                 for sp, idxs in sorted(fn_map[fn].items()):
                     idx_str = "/".join(str(i) for i in sorted(idxs))
                     entries.append(f"{sp} ({idx_str})")
                 if entries:
                     remarks_lines.append(f"{fn}: {', '.join(entries)}")

        # Exception: Rugstreeppad + Specific Function -> Specific Remark
        # "platen neerleggen, eisnoeren/larven"
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
            
        # Exception: Family 'Vlinder' (Any Function) -> Specific Remark
        has_vlinder = False
        for r in assigned_reqs:
             p = r.protocol
             fam_name = getattr(getattr(getattr(p, "species", None), "family", None), "name", "")
             if fam_name == "Vlinder":
                 has_vlinder = True
                 break
        
        if has_vlinder:
            remarks_lines.append("Min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (met meer >50% bewolking)")
            
        # Exception: Family 'Langoren' (Any Function) -> Specific Remark
        has_langoren = False
        for r in assigned_reqs:
             p = r.protocol
             fam_name = getattr(getattr(getattr(p, "species", None), "family", None), "name", "")
             if fam_name == "Langoren":
                 has_langoren = True
                 break
        
        if has_langoren:
            remarks_lines.append("Geen mist, sneeuwval. Bodemtemperatuur < 15 graden")
            
        if remarks_lines:
             new_visit.remarks_field = "\n".join(remarks_lines)
        
        if default_remarks_field:
            if new_visit.remarks_field:
                new_visit.remarks_field += "\n" + default_remarks_field
            else:
                new_visit.remarks_field = default_remarks_field
        
        # Calculate Series Start Date for sorting (tie-breaker for same-day visits)
        # We want to visit "Function A (Visit 3)" before "Function B (Visit 1)" if they are on same day.
        # Implies prioritizing the "Older" series.
        series_starts = []
        for p in unique_protos:
            if p.visit_windows:
                # Assuming windows are sorted or first one is start
                # Use min() to be safe
                series_starts.append(min(w.window_from for w in p.visit_windows))
        
        new_visit._sort_series_start = min(series_starts) if series_starts else date.max

        visits.append(new_visit)
        
    # Sort visits chronologically and assign consecutive numbers
    # Primary: Date. Secondary: Series Start Date (Oldest series first). Tertiary: Morning < Evening.
    visits.sort(key=lambda x: (
        x.from_date or date.max,
        getattr(x, "_sort_series_start", date.max),
        0 if x.part_of_day == "Ochtend" else 1 if x.part_of_day == "Dag" else 2
    ))
    
    for i, v in enumerate(visits):
        v.visit_nr = i + 1
        db.add(v)
        
        if _DEBUG_VISIT_GEN:
             _logger.info("  -> Created Visit %d: %s %s (%s)", v.visit_nr, v.from_date, v.part_of_day, v.remarks_field)

    return visits, warnings

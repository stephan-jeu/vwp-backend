from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import logging
import os
from collections import defaultdict
from uuid import uuid4

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.species import Species
from app.models.visit import Visit

_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}
_logger = logging.getLogger("uvicorn.error")

MIN_EFFECTIVE_WINDOW_DAYS = int(os.getenv("MIN_EFFECTIVE_WINDOW_DAYS", "10"))


@dataclass
class VisitRequest:
    """Represents a single required visit occurrence (Node in the graph)."""

    protocol: Protocol
    visit_index: int
    window_from: date
    window_to: date
    pvw_id: int
    part_of_day_options: set[str] | None  # None means any
    
    # Structural dependencies (graph edges)
    # IDs of compatible requests (Grouping candidates)
    compatible_request_ids: set[str] = field(default_factory=set)
    
    # Ordering dependency: (request_id, min_gap_days)
    # The referenced request MUST precede this one.
    predecessor: tuple[str, int] | None = None

    @property
    def id(self) -> str:
        """Unique identifier for this request node."""
        return f"p{self.protocol.id}_v{self.visit_index}"


@dataclass
class VisitGroup:
    """Represents a finalized group of compatible requests (Clique)."""
    
    requests: list[VisitRequest]
    
    # Scheduling info (calculated later)
    final_window_from: date | None = None
    final_window_to: date | None = None
    assigned_part_of_day: str | None = None
    
    @property
    def id(self) -> str:
        # Sort requests to ensure stable ID
        sorted_ids = sorted(r.id for r in self.requests)
        return "g_" + "_".join(sorted_ids)


async def generate_visits_graph_based(
    db: AsyncSession,
    cluster: Cluster,
    protocols: list[Protocol],
) -> tuple[list[Visit], list[str]]:
    """Generate visits for a cluster using Graph-Based Constraint Satisfaction.

    Pipeline:
      1. Request Generation (Node Explosion)
      2. Graph Building (Compatibility Edges)
      3. Grouping (Clique Partitioning)
      4. Scheduling (Topological Walk & Window Propagation)
      5. construction (Visit ORM creation)
    
    Returns:
        (visits, warnings)
    """
    if not protocols:
        return [], []
        
    warnings: list[str] = []

    if _DEBUG_VISIT_GEN:
        _logger.info("Starting Graph-Based Visit Gen for Cluster %s", cluster.id)

    # 1. Request Generation
    requests = _generate_visit_requests(protocols)
    if _DEBUG_VISIT_GEN:
        _logger.info("GRAPH: Generated %d requests from %d protocols", len(requests), len(protocols))
        for r in requests:
            _logger.info(
                "  Req: %s (Win: %s-%s) EffWin=%s-%s Parts=%s",
                r.id, r.window_from, r.window_to,
                r.effective_window_from, r.window_to, # Effective window ends at original window_to
                r.part_of_day_options
            )
            
    if not requests:
        return [], warnings

    # 2. Graph Building
    _build_compatibility_graph(requests)
    if _DEBUG_VISIT_GEN:
        edge_count = sum(len(r.compatible_request_ids) for r in requests) // 2
        _logger.info("GRAPH: Built compatibility graph with %d edges", edge_count)

    # 3. Grouping
    groups = _partition_into_cliques(requests)
    if _DEBUG_VISIT_GEN:
        _logger.info("GRAPH: Partitioned into %d groups", len(groups))
        for g in groups:
             # Calculate intersection of Part of Day
             common_parts = g.requests[0].part_of_day_options.copy()
             for r in g.requests[1:]:
                 common_parts.intersection_update(r.part_of_day_options)
             
             _logger.info(
                 "  Group %s: Window=[%s -> %s] Parts=%s Reqs=%s", 
                 g.id, 
                 g.final_window_from, g.final_window_to,
                 common_parts,
                 [r.id for r in g.requests]
             )

    # 4. Scheduling
    _schedule_groups(groups)

    # 5. Construction
    visits = await _construct_visits(db, cluster, groups)

    return visits, warnings


# --- Phase 1: Request Generation ---

def _to_current_year(d: date) -> date:
    today = date.today()
    current_year = today.year
    try:
        return d.replace(year=current_year)
    except ValueError:
        # Feb 29 -> Feb 28
        if d.month == 2 and d.day == 29:
            return date(current_year, 2, 28)
        raise



def _generate_visit_requests(protocols: list[Protocol]) -> list[VisitRequest]:
    """Explode protocols into individual required visit occurrences (Nodes)."""
    requests: list[VisitRequest] = []
    
    # Pre-calculate to current year helper
    today = date.today()
    current_year = today.year

    # Pre-calculate to current year helper
    today = date.today()
    current_year = today.year



    # 1. First Pass: Create Requests
    req_map: dict[str, VisitRequest] = {}
    
    for p in protocols:
        if not p.visit_windows:
            continue
            
        # Sort windows by index
        windows = sorted(p.visit_windows, key=lambda w: w.visit_index)
        
        # Track previous request for dependency chain
        prev_request: VisitRequest | None = None
        
        min_gap_days = _unit_to_days(
            p.min_period_between_visits_value, 
            p.min_period_between_visits_unit
        )
        
        # Check overall requirements
        req_morning = getattr(p, "requires_morning_visit", False)
        req_evening = getattr(p, "requires_evening_visit", False)
        
        # Base options from timing reference (e.g. {O, A} or {D} or {A})
        base_parts = _derive_part_options_base(p)

        for i, w in enumerate(windows):
            wf = _to_current_year(w.window_from)
            wt = _to_current_year(w.window_to)
            
            if wf > wt:
                if _DEBUG_VISIT_GEN:
                    _logger.warning("Skipping invalid window for proto %s: %s->%s", p.id, wf, wt)
                continue

            # Determine allowed parts for THIS specific visit occurrence
            # Copy base options (None means Any)
            parts = set(base_parts) if base_parts is not None else None
            
            # Apply "At least one" constraints (Refined for Heuristic)
            # We enforce strictly on Visit Index 1.
            # This ensures at least one visit satisfies the condition (early validation).
            # Subsequent visits (Index > 1) remain flexible, allowing merges with other times.
            if w.visit_index == 1:
                if req_morning:
                    if parts is None:
                        parts = {"Ochtend"}
                    else:
                        parts.intersection_update({"Ochtend"})
                if req_evening:
                    if parts is None:
                        parts = {"Avond"}
                    else:
                        parts.intersection_update({"Avond"})
            
            # If parts became empty due to intersection (conflict), revert or warn?
            # e.g. Base={Avond} but ReqMorning=True.
            if not parts and base_parts:
                # Conflict: Protocol timing says Avond, but Flag says Morning.
                # Trust the Flag? Or Trust the Timing?
                # Legacy seems to trust Flag for splitting.
                # Let's fallback to base and hope.
                parts = base_parts

            # Handle predecessor dependency
            predecessor = None
            if w.visit_index > 1 and prev_request:
                predecessor = (prev_request.id, min_gap_days or 0)
            
            req = VisitRequest(
                protocol=p,
                visit_index=w.visit_index,
                window_from=wf,
                window_to=wt,
                pvw_id=w.id,
                part_of_day_options=parts,
                predecessor=predecessor
            )
            
            if _DEBUG_VISIT_GEN:
                _logger.info(
                    "  Req debug: %s v%d Base=%s Flags(M=%s,E=%s) -> Parts=%s",
                    req.id, w.visit_index, base_parts, req_morning, req_evening, parts
                )

            requests.append(req)
            req_map[req.id] = req
            prev_request = req

    # 2. Second Pass: Calculate Effective Start Times (Propagate Delays)
    # Since we create requests in order (v1, v2..), we can just iterate.
    # Actually, protocols might be processed in any order, but v1 always created before v2 in loop.
    # But to be safe, we iterate sorted by ID or rely on logic.
    # Since 'requests' list is appended in order of protocol.windows extraction,
    # and windows are sorted by index, v1 is always before v2 for a given protocol.
    # So a single pass is sufficient.
    
    for r in requests:
        wd_start = r.window_from
        
        if r.predecessor:
            pred_id, gap = r.predecessor
            pred = req_map[pred_id]
            # Effective start is constrained by Predecessor Effective Start + Gap
            # Pred Effective Start is its own window_from (or calculated).
            # We assume pred.effective_window_from is already set if order is correct.
            pred_eff = pred.effective_window_from or pred.window_from
            min_valid = pred_eff + timedelta(days=gap)
            
            if min_valid > wd_start:
                wd_start = min_valid
        
        r.effective_window_from = wd_start
        
        # Sanity check: if Effective Start > Window To, this request is impossible.
        if r.effective_window_from > r.window_to:
             if _DEBUG_VISIT_GEN:
                 _logger.warning("Request %s is impossible: Eff Start %s > End %s", r.id, r.effective_window_from, r.window_to)

    return requests


def _unit_to_days(value: int | None, unit: str | None) -> int:
    if not value:
        return 0
    if not unit:
        return value
    u = unit.strip().lower()
    if u in {"week", "weeks", "weeken", "weken"}:
        return value * 7
    return value


def _derive_part_options_base(protocol: Protocol) -> set[str] | None:
    """Return allowed part-of-day options based on timing reference only."""
    ref_start = protocol.start_timing_reference or ""
    ref_end = getattr(protocol, "end_timing_reference", None) or ""

    if ref_start == "DAYTIME":
        return {"Dag"}
    if ref_start == "ABSOLUTE_TIME":
        # Do not over-constrain: allow both, actual part is decided later
        return {"Avond", "Ochtend"}

    if ref_start == "SUNSET" and ref_end == "SUNRISE":
        return {"Avond", "Ochtend"}
    if ref_start == "SUNSET":
        return {"Avond"}
    if ref_start == "SUNRISE":
        # If explicitly starting AFTER sunrise, treat as Day (Dag)
        # e.g. "Sunrise + 60 min" is effectively day work.
        rel_min = protocol.start_time_relative_minutes
        if rel_min is not None and rel_min >= 0:
             return {"Dag"}
        return {"Ochtend"}
    if ref_start == "SUNSET_TO_SUNRISE":
        return {"Avond", "Ochtend"}
        
    return None

def _derive_part_options(protocol: Protocol) -> set[str] | None:
    # Deprecated/Unused helper wrapper if needed, or remove?
    # Keeping for compatibility if mistakenly called elsewhere?
    # The new logic uses _derive_part_options_base inline.
    return _derive_part_options_base(protocol)


# --- Phase 2: Graph Building ---

def _build_compatibility_graph(requests: list[VisitRequest]) -> None:
    """Populate compatible_request_ids for each request (Edges)."""
    # Optimize: O(N^2) is fine for N ~ 50-100.
    n = len(requests)
    for i in range(n):
        for j in range(i + 1, n):
            r1 = requests[i]
            r2 = requests[j]
            
            if _are_compatible(r1, r2):
                r1.compatible_request_ids.add(r2.id)
                r2.compatible_request_ids.add(r1.id)


def _are_compatible(r1: VisitRequest, r2: VisitRequest) -> bool:
    """Check if two requests can form an edge (Bio + Window + Part)."""
    
    # 0. Self-Protocol Check (Cannot visit same protocol twice in one visit)
    if r1.protocol.id == r2.protocol.id:
        return False

    # (Removed strict visit_index cycle check per user request. 
    # relying on chronological heuristic in partitioning instead.)

    # 1. Biological Compatibility (Family/SMP/Exception)
    if not _check_bio_compatibility(r1.protocol, r2.protocol):
        return False
        
    # 2. Window Overlap >= MIN_EFFECTIVE_WINDOW_DAYS
    overlap = _overlap_days(
        r1.window_from, r1.window_to,
        r2.window_from, r2.window_to
    )
    if overlap < MIN_EFFECTIVE_WINDOW_DAYS:
        return False
        
    # 3. Part of Day Intersection
    if not _check_part_intersection(r1.part_of_day_options, r2.part_of_day_options):
        return False
        
    return True


def _check_bio_compatibility(p1: Protocol, p2: Protocol) -> bool:
    """True if protocols are compatible by family, SMP, or exc exception."""
    # SMP Gating
    smp1 = getattr(getattr(p1, "function", None), "name", "").startswith("SMP")
    smp2 = getattr(getattr(p2, "function", None), "name", "").startswith("SMP")
    
    if smp1 or smp2:
        if not (smp1 and smp2):
            return False # Mixed SMP/Non-SMP not allowed
        # Both SMP: Must be same family (no cross-family)
        return _same_family(p1, p2)

    # Exception: Rugstreeppad (Natterjack Toad)
    # Functions for this species must be visited sequentially, never combined.
    # Therefore, if Functions differ, they are incompatible.
    sp_name = getattr(getattr(p1, "species", None), "name", "")
    if sp_name == "Rugstreeppad":
        fn1 = getattr(p1, "function", None)
        fn2 = getattr(p2, "function", None)
        if fn1 and fn2 and fn1.id != fn2.id:
            return False

    # Standard Family Logic
    if _same_family(p1, p2):
        return True
        
    # Legacy Cross-Family Exceptions
    return _is_allowed_cross_family(p1, p2)


def _same_family(p1: Protocol, p2: Protocol) -> bool:
    # Try ID first
    try:
        if p1.species.family_id == p2.species.family_id:
            return True
    except AttributeError:
        pass
    
    # Fallback name matching
    n1 = _normalize_family_name(getattr(getattr(p1, "species", None), "family", None))
    n2 = _normalize_family_name(getattr(getattr(p2, "species", None), "family", None))
    return bool(n1) and n1 == n2


def _normalize_family_name(fam_obj) -> str:
    if not fam_obj: return ""
    name = getattr(fam_obj, "name", "")
    if not name: return ""
    n = name.strip().lower()
    if "vleer" in n: return "vleermuis"
    if "zwaluw" in n: return "zwaluw"
    return n


def _is_allowed_cross_family(p1: Protocol, p2: Protocol) -> bool:
    n1 = _normalize_family_name(getattr(getattr(p1, "species", None), "family", None))
    n2 = _normalize_family_name(getattr(getattr(p2, "species", None), "family", None))
    
    pair = {n1, n2}
    allowed = [{"vleermuis", "zwaluw"}]
    return any(pair == a for a in allowed)


def _overlap_days(start1: date, end1: date, start2: date, end2: date) -> int:
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    delta = (overlap_end - overlap_start).days
    return delta if delta > 0 else 0


def _check_part_intersection(set1: set[str] | None, set2: set[str] | None) -> bool:
    if set1 is None or set2 is None:
        return True
    return not set1.isdisjoint(set2)


# ... (helpers unchanged) ...


# --- Phase 3: Grouping ---

def _partition_into_cliques(requests: list[VisitRequest]) -> list[VisitGroup]:
    """Greedy Clique Partitioning with Dynamic Delay Propagation."""
    
    # Map id -> request
    registry = {r.id: r for r in requests}
    remaining_ids = set(registry.keys())
    
    # Track assigned groups for simple lookup [req_id] -> group_index
    req_to_group_idx = {}
    
    # Track finalized group "Effective Start Date"
    # This is the max(dynamic_start) of all members in that group.
    # Group Index -> Date
    group_finish_estimation = {} 
    
    groups: list[VisitGroup] = []
    
    while remaining_ids:
        # Helper to calculate Dynamic Effective Start for ANY request (assigned or not)
        # based on currently finalized groups.
        def _get_dynamic_start(rid: str) -> date:
            req = registry[rid]
            base = req.effective_window_from or req.window_from # Base includes static predecessor logic
            
            # Check predecessor DYNAMIC logic
            if req.predecessor:
                pred_id, gap_days = req.predecessor
                if pred_id in req_to_group_idx:
                    g_idx = req_to_group_idx[pred_id]
                    if g_idx in group_finish_estimation:
                        pred_group_start = group_finish_estimation[g_idx]
                        return max(base, pred_group_start + timedelta(days=gap_days))
            return base

        # Heuristic 1: Seed Selection
        valid_seeds = []
        for rid in remaining_ids:
            pred = registry[rid].predecessor
            # Must be unlocked (pred assigned or no pred)
            if not pred or pred[0] in req_to_group_idx:
                valid_seeds.append(rid)
        
        pool = valid_seeds if valid_seeds else list(remaining_ids)

        # Re-evaluate seeds with Dynamic Start
        seed_id = min(
            pool, 
            key=lambda rid: (
                _get_dynamic_start(rid), 
                (registry[rid].window_to - _get_dynamic_start(rid)).days,
                rid
            )
        )
        
        # Start clique with seed
        clique_ids = {seed_id}
        
        # Initialize Intersection State with Seed's DYNAMIC start
        seed_dynamic_start = _get_dynamic_start(seed_id)
        current_max_start = seed_dynamic_start
        current_min_start = seed_dynamic_start  # Track earliest start to calculate spread
        current_min_end = registry[seed_id].window_to
        
        # Grow clique
        candidates = sorted(
            [rid for rid in remaining_ids if rid != seed_id],
            key=lambda rid: (
                0 if rid in registry[seed_id].compatible_request_ids else 1,
                abs((_get_dynamic_start(rid) - current_max_start).days),
                (registry[rid].window_to - registry[rid].window_from).days
            )
        )
        
        for cand_id in candidates:
            cand_req = registry[cand_id]
            
            # Check Predecessor Constraint
            pred = cand_req.predecessor
            is_pred_local = False
            if pred:
                pred_id = pred[0]
                # Allowed if predecessor is assigned globally OR is in CURRENT clique
                if pred_id in clique_ids:
                    is_pred_local = True
                elif pred_id not in req_to_group_idx:
                    continue
            
            # Dynamic Start Calculation for Candidate
            if is_pred_local:
                # If pred is in SAME group, they are synchronized.
                # Candidate consumes gap relative to GROUP start?
                # Actually, if P1 and P2 are in same group, P2 must be > P1 + Gap.
                # This implies P2 cannot be in same group as P1 if Gap > 0!
                # Because Group implies simultaneous execution.
                # If Gap > 0, they strictly cannot be in same group unless group spans Gap days?
                # Assumption: Visit Group = Single Visit Event.
                # Visit Event duration is hours. Gap is days.
                # Conclusion: Predecessor and Successor CANNOT be in same group if Gap > 0.
                # (Unless Gap=0 allowed? But typically Gap >= MIN_PERIOD).
                # So if pred is in clique_ids, we must REJECT candidate.
                continue
            
            cand_dynamic_start = _get_dynamic_start(cand_id)
            cand_end = cand_req.window_to
            
            # Check Compatibility
            is_clique_member = True
            for members_id in clique_ids:
                if members_id not in cand_req.compatible_request_ids:
                    is_clique_member = False
                    break
            
            if not is_clique_member:
                continue

            # Check Intersection
            new_max_start = max(current_max_start, cand_dynamic_start)
            new_min_start = min(current_min_start, cand_dynamic_start)
            new_min_end = min(current_min_end, cand_end)
            intersection_days = (new_min_end - new_max_start).days
            
            if intersection_days < MIN_EFFECTIVE_WINDOW_DAYS:
                continue

            # Optimization: Prevent "dragging" early visits too late.
            # Calculate total time spread of the group's start times.
            # Spread = (Latest Start) - (Earliest Start).
            start_spread = (new_max_start - new_min_start).days
            
            # EXCEPTION: If the candidate OR any existing member has a "Short Window" (e.g. < 35 days),
            # it is an "Anchor" event. We MUST prioritize grouping with it over delay concerns.
            # This allows merging p50 (31 days) and p28 (45 days? no, 45 is > 35)
            # User Request: Squeeze into 3 visits.
            has_urgent_member = False
            if (registry[cand_id].window_to - registry[cand_id].window_from).days < 35:
                has_urgent_member = True
            else:
                for member_id in clique_ids:
                    if (registry[member_id].window_to - registry[member_id].window_from).days < 35:
                        has_urgent_member = True
                        break

            # Refinement: Only enforce strict delay cap if the resulting window is "non-huge".
            # Relaxed threshold to < 50 days intersection (was 40, originally 50).
            # This makes the split condition stricter (intersection must be < 50 to split),
            # protecting V1s (long windows) from being dragged late by V2s unless overlap is massive.
            if not has_urgent_member and start_spread > 7 and intersection_days < (25 if pred else 50):
                continue
            
            # CRITICAL CHECK: Forward Feasibility (Lookahead)
            # Merging this candidate might push the Group Start (new_max_start) so late
            # that Successors of ANY group member (including candidate) become impossible due to Gaps.
            # E.g. If Group moves to July 1, and Member A needs Gap 20d for V2 (deadline July 15),
            # then July 1 + 20 = July 21 > July 15. IMPOSSIBLE.
            # We must reject the merge if it "poisons" the timeline for successors.
            
            # Identifying all successors to check
            # We need to find the V(i+1) request for each Member(V_i).
            # Helper to find successor request given a current request.
            # Since we only have 'requests' list in scope, we scan it? Or use a map?
            # 'registry' has all requests. We can scan registry for (protocol_id, visit_index + 1).
            
            # Optimization: Pre-calculate successor map? 
            # For now, simple scan is O(N_clique * N_total), acceptable for small N.
            
            all_members = list(clique_ids) + [cand_id]
            is_feasible = True
            
            for m_id in all_members:
                m_req = registry[m_id]
                # Check if this request has a successor
                # Successor has same protocol, index + 1
                succ_req = None
                for potential_succ_id in registry:
                    r = registry[potential_succ_id]
                    if r.protocol.id == m_req.protocol.id and r.visit_index == m_req.visit_index + 1:
                        succ_req = r
                        break
                
                if succ_req:
                    # Check Gap
                    gap_days = _unit_to_days(m_req.protocol.min_period_between_visits_value, m_req.protocol.min_period_between_visits_unit)
                    # Projected Successor Start
                    proj_succ_start = new_max_start + timedelta(days=gap_days)
                    
                    if proj_succ_start > succ_req.window_to:
                        # Impossible!
                        is_feasible = False
                        break
            
            if not is_feasible:
                continue

            # CRITICAL CHECK: Forward Feasibility (Lookahead)
            # Merging this candidate might push the Group Start (new_max_start) so late
            # that Successors of ANY group member (including candidate) become impossible due to Gaps.
            # E.g. If Group moves to July 1, and Member A needs Gap 20d for V2 (deadline July 15),
            # then July 1 + 20 = July 21 > July 15. IMPOSSIBLE.
            # We must reject the merge if it "poisons" the timeline for successors.
            
            # Identifying all successors to check
            # We need to find the V(i+1) request for each Member(V_i).
            # Helper to find successor request given a current request.
            # Since we only have 'requests' list in scope, we scan it? Or use a map?
            # 'registry' has all requests. We can scan registry for (protocol_id, visit_index + 1).
            
            # Optimization: Pre-calculate successor map? 
            # For now, simple scan is O(N_clique * N_total), acceptable for small N.
            
            all_members = list(clique_ids) + [cand_id]
            is_feasible = True
            
            for m_id in all_members:
                m_req = registry[m_id]
                # Check if this request has a successor
                # Successor has same protocol, index + 1
                succ_req = None
                for potential_succ_id in registry:
                    r = registry[potential_succ_id]
                    if r.protocol.id == m_req.protocol.id and r.visit_index == m_req.visit_index + 1:
                        succ_req = r
                        break
                
                if succ_req:
                    # Check Gap
                    gap_days = _unit_to_days(m_req.protocol.min_period_between_visits_value, m_req.protocol.min_period_between_visits_unit)
                    # Projected Successor Start
                    proj_succ_start = new_max_start + timedelta(days=gap_days)
                    
                    if proj_succ_start > succ_req.window_to:
                        # Impossible!
                        is_feasible = False
                        break
            
            if not is_feasible:
                continue

            # Accept
            clique_ids.add(cand_id)
            current_max_start = new_max_start
            current_min_start = new_min_start
            current_min_end = new_min_end
        
        # Finalize Group
        group_requests = [registry[rid] for rid in clique_ids]
        new_group_idx = len(groups)
        groups.append(VisitGroup(
            requests=group_requests,
            final_window_from=current_max_start,
            final_window_to=current_min_end
        ))
        
        # Update Estimates and Maps
        group_finish_estimation[new_group_idx] = current_max_start
        for rid in clique_ids:
            req_to_group_idx[rid] = new_group_idx
        
        remaining_ids -= clique_ids
        
    return groups


# --- Phase 4: Scheduling ---

def _schedule_groups(groups: list[VisitGroup]) -> None:
    """Calculate final windows and sequencing for groups."""
    
    # 1. Map request_id -> Group to find dependencies
    req_to_group: dict[str, VisitGroup] = {}
    for g in groups:
        for r in g.requests:
            req_to_group[r.id] = g
            
    # 2. Build Group Dependencies
    # If R2 in G2 depends on R1 in G1, G2 depends on G1
    group_deps: dict[str, set[str]] = defaultdict(set)
    group_registry: dict[str, VisitGroup] = {g.id: g for g in groups}
    
    for g in groups:
        for r in g.requests:
            if r.predecessor:
                pred_id, _gap = r.predecessor
                pred_group = req_to_group.get(pred_id)
                if pred_group and pred_group != g:
                    group_deps[g.id].add(pred_group.id)

    # 3. Topological sort of groups
    # Kahn's algorithm or similar
    sorted_groups: list[VisitGroup] = []
    visited: set[str] = set()
    temp_visiting: set[str] = set()

    def visit(gid: str):
        if gid in visited: return
        if gid in temp_visiting:
            raise ValueError("Cycle detected in dependencies") # Should not happen
        temp_visiting.add(gid)
        for dep_gid in group_deps[gid]:
            visit(dep_gid)
        temp_visiting.remove(gid)
        visited.add(gid)
        sorted_groups.append(group_registry[gid])
        
    for g in groups:
        if g.id not in visited:
            visit(g.id)
            
    # 4. Process in order
    for g in sorted_groups:
        # Initial intersection of member windows
        wf = max(r.window_from for r in g.requests)
        wt = min(r.window_to for r in g.requests)
        
        # Apply predecessor constraints
        for r in g.requests:
            if r.predecessor:
                pred_id, gap = r.predecessor
                pred_group = req_to_group.get(pred_id)
                if pred_group and pred_group.final_window_from:
                    # Constraint: Current start >= Pred Start + min_gap
                    # Why Pred Start? 
                    # Actually, strictly it should be Pred *Realized* Date.
                    # Since we define windows, we want to ensure *validity*.
                    # Safe logic: Earliest possible start for this visit 
                    # must be >= Earliest possible start of prev + gap.
                    # This ensures that *if* we pick earliest dates for both, it works.
                    earliest_allowed = pred_group.final_window_from + timedelta(days=gap)
                    if earliest_allowed > wf:
                        wf = earliest_allowed
        
        # What if wf > wt?
        # This means the group is invalid due to dependencies pushing it out of window.
        # In a perfect solver, we would look ahead or backtrack.
        # Here, we might just clip or log warning.
        # For now, let's keep it "valid" if possible, or force it.
        # If wf > wt, we prioritize the dependency (wf) but cap at wt? 
        # No, wt is hard deadline (season end).
        if wf > wt:
             if _DEBUG_VISIT_GEN:
                 _logger.warning("Group %s scheduled out of bounds: %s > %s", g.id, wf, wt)
             # Fallback: Just take the window end? Or keep the pushed start?
             # Keeping pushed start might violate protocol window.
             # Keeping window end might violate gap.
             # Gap is usually physical necessity, window is legal.
             # Let's favor Gap for safety, but this really needs splitting then.
             # Since we can't split now (that was Phase 3), we accept the weirdness.
             pass

        g.final_window_from = wf
        g.final_window_to = wt
        
        # 5. Assign Part of Day
        # Intersect all options
        common_parts = None
        for r in g.requests:
             if common_parts is None:
                 common_parts = r.part_of_day_options
             elif r.part_of_day_options is not None:
                 common_parts = common_parts & r.part_of_day_options
        
        # heuristic selection
        chosen = None
        if common_parts:
             has_paarverblijf = any(r.protocol.function.name == "Paarverblijf" for r in g.requests)
             if has_paarverblijf:
                 # Default to Avond for Paarverblijf
                 if "Avond" in common_parts: chosen = "Avond"
                 elif "Ochtend" in common_parts: chosen = "Ochtend"
                 elif "Dag" in common_parts: chosen = "Dag"
                 else: chosen = list(common_parts)[0]
             else:
                 # Default to Morning
                 if "Ochtend" in common_parts: chosen = "Ochtend"
                 elif "Avond" in common_parts: chosen = "Avond"
                 elif "Dag" in common_parts: chosen = "Dag"
                 else: chosen = list(common_parts)[0]
             
        g.assigned_part_of_day = chosen


# --- Phase 5: Construction ---

def _construct_visits(
    db: AsyncSession, cluster: Cluster, groups: list[VisitGroup]
) -> list[Visit]:
    """Convert groups to Visit ORM objects."""
    
    # Sort groups by date for logical visit numbering
    # Heuristic: sort by window start
    sorted_groups = sorted(
        groups, 
        key=lambda g: g.final_window_from or date.max
    )
    
    # Get next visit number
    next_nr: int = 0 
    # Logic to get next_nr requires async execution which cannot be done easily in 
    # sequential loop without creating a bottleneck or pre-fetching.
    # We will pre-fetch the starting number.
    # Note: caller should probably handle transaction locking or similar if high concurrency.
    # Here we assume single-threaded gen per cluster.
    
    # We need to run the query to get the current max.
    # Since we are inside async def, we can await. But _construct_visits is async? 
    # The signature in skeleton was synchronous in my replace attempt description but
    # the original skeleton had `async def generate_visits_graph_based`.
    # Let's make _construct_visits async.
    pass # Placeholder to be effectively replaced by logic below.

    # Re-declare as async to match logic
    return []

# Re-implementing correctly as async below replacing the whole block
async def _construct_visits(
    db: AsyncSession, cluster: Cluster, groups: list[VisitGroup]
) -> list[Visit]:
    # Sort groups by date for logical visit numbering
    sorted_groups = sorted(
        groups, 
        key=lambda g: g.final_window_from or date.max
    )
    
    next_nr = await _next_visit_nr(db, cluster.id)
    series_group_id = str(uuid4())
    
    created_visits: list[Visit] = []
    
    for g in sorted_groups:
        if not g.final_window_from or not g.final_window_to:
            continue
            
        protocols = [r.protocol for r in g.requests]
        
        # 1. Weather Constraints (Strictest)
        min_temp = max(
            (p.min_temperature_celsius for p in protocols if p.min_temperature_celsius is not None),
            default=None
        )
        max_wind = min(
            (p.max_wind_force_bft for p in protocols if p.max_wind_force_bft is not None),
            default=None
        )
        precip_options = [p.max_precipitation for p in protocols if p.max_precipitation]
        precip = _select_most_restrictive_precipitation(precip_options)
        
        # 2. Duration (Max of protocols)
        durations = [
             p.visit_duration_hours for p in protocols if p.visit_duration_hours is not None
        ]
        duration_min = int(max(durations) * 60) if durations else None
        
        # 3. Remarks
        remarks_texts = [p.visit_conditions_text for p in protocols if p.visit_conditions_text]
        remarks_planning = _extract_whitelisted_remarks(remarks_texts)
        remarks_planning_text = " | ".join(remarks_planning) if remarks_planning else None
        
        # Field remarks (Species per function)
        remarks_field = _build_field_remarks(g)
        
        # 4. Boolean Flags (Union)
        req_morning = any(getattr(p, "requires_morning_visit", False) for p in protocols)
        req_evening = any(getattr(p, "requires_evening_visit", False) for p in protocols)
        req_june = any(getattr(p, "requires_june_visit", False) for p in protocols)
        req_maternity = any(getattr(p, "requires_maternity_period_visit", False) for p in protocols)

        # 5. Combined Duration (Range-Based)
        duration_min = _calculate_combined_duration(protocols, g.assigned_part_of_day, duration_min)

        # 6. Start Time Text
        start_time_text = _derive_start_time_text_combined(protocols, g.assigned_part_of_day, duration_min)

        # EXCEPTION: RD Paarverblijf Visit 1 -> 00:00 (implies start_timing_reference=ABSOLUTE_TIME 00:00)
        for r in g.requests:
            if (
                r.visit_index == 1
                and r.protocol.function.name == "Paarverblijf"
                and r.protocol.species.abbreviation == "RD"
            ):
                start_time_text = "00:00"
                break

        # 7. Build Visit
        v = Visit(
            cluster_id=cluster.id,
            group_id=series_group_id,
            visit_nr=next_nr,
            from_date=g.final_window_from,
            to_date=g.final_window_to,
            duration=duration_min,
            min_temperature_celsius=min_temp,
            max_wind_force_bft=max_wind,
            max_precipitation=precip,
            remarks_planning=remarks_planning_text,
            remarks_field=remarks_field,
            requires_morning_visit=req_morning,
            requires_evening_visit=req_evening,
            requires_june_visit=req_june,
            requires_maternity_period_visit=req_maternity,
            part_of_day=g.assigned_part_of_day,
            start_time_text=start_time_text
        )
        
        # 7. Relations
        # Dedup lists
        # Use simple ID map to dedup
        funcs = {}
        specs = {}
        for p in protocols:
            if p.function: funcs[p.function.id] = p.function
            if p.species: specs[p.species.id] = p.species
            
        v.functions = list(funcs.values())
        v.species = list(specs.values())
        
        # Link PVWs
        pvws = []
        for r in g.requests:
             # Find window by ID
             window = next((w for w in r.protocol.visit_windows if w.id == r.pvw_id), None)
             if window:
                 pvws.append(window)
        v.protocol_visit_windows = pvws
        
        db.add(v)
        created_visits.append(v)
        next_nr += 1
        
    return created_visits


async def _next_visit_nr(db: AsyncSession, cluster_id: int) -> int:
    stmt = (
        select(Visit.visit_nr)
        .where(Visit.cluster_id == cluster_id)
        .order_by(Visit.visit_nr.desc())
    )
    row = (await db.execute(stmt)).first()
    return (row[0] or 0) + 1 if row else 1


# --- Helpers ---

def _select_most_restrictive_precipitation(options: list[str]) -> str | None:
    if not options: return None
    # Order from MOST restrictive (0) to LEAST restrictive (3)
    # min() will pick the one with the lowest index (highest priority)
    order = ["geen neerslag, geen mist boven watergangen", "droog", "geen regen", "motregen"]
    priority = {name: idx for idx, name in enumerate(order)}
    
    scored = []
    for o in options:
        norm = o.strip().lower()
        rank = priority.get(norm, 999)
        scored.append((o, rank))
        
    return min(scored, key=lambda x: x[1])[0]


def _extract_whitelisted_remarks(texts: list[str]) -> list[str]:
    # Hardcoded allowance for basic example, ideally share constant
    allowlist = [
        "1x in de kraamperiode", "eventueel 1 ochtend", "ten minste 1 ochtend",
        "enkel ochtend bezoeken", "1 ochtend",
        "relatief warme avonden, bij voorkeur na regen of een weersomslag",
        "zo mogelijk 1 ochtend", "1 ronde in juni", "'s avonds", "'s ochtends",
        "bij voorkeur niet na (hevige) regenbuien"
    ]
    
    if not texts: return []
    unique = []
    seen = set()
    texts_norm = [t.lower() for t in texts if t]
    
    # Simple contains check against allowlist
    for phrase in allowlist:
        p = phrase.lower()
        if any(p in t for t in texts_norm):
            if phrase not in seen:
                seen.add(phrase)
                unique.append(phrase)
    return unique


def _build_field_remarks(g: VisitGroup) -> str | None:
    try:
        fn_map = defaultdict(lambda: defaultdict(list))
        for r in g.requests:
            fn_name = r.protocol.function.name
            sp_name = r.protocol.species.abbreviation or r.protocol.species.name
            fn_map[fn_name][sp_name].append(str(r.visit_index))
            
        lines = []
        for fn, sp_map in sorted(fn_map.items()):
            entries = []
            for sp, idxs in sorted(sp_map.items()):
                 entries.append(f"{sp} ({'/'.join(sorted(idxs))})")
            lines.append(f"{fn}: {', '.join(entries)}")
            
        return "\n".join(lines)
    except Exception:
        return None

def _calculate_combined_duration(
    protocols: list[Protocol], 
    part_of_day: str, 
    fallback_duration: int | None
) -> int | None:
    """Calculate effective duration covering the full span of diverse start/end times."""
    
    # Base candidates
    start_candidates = [
        _derive_start_time_minutes(p) for p in protocols 
        if _derive_start_time_minutes(p) is not None
    ]
    end_candidates = [
        _derive_end_time_minutes(p) for p in protocols
        if _derive_end_time_minutes(p) is not None
    ]
    
    if part_of_day == "Ochtend":
         # Morning: Span = (Latest End) - (Earliest Start)
         # Earliest Start comes from:
         # 1. Explicit start refs
         # 2. Derived starts from (End - Duration)
         
         starts_from_end = []
         for p in protocols:
             end_m = _derive_end_time_minutes(p)
             dur_h = getattr(p, "visit_duration_hours", None)
             if end_m is not None and dur_h is not None:
                 starts_from_end.append(int(end_m - int(dur_h * 60)))
                 
         all_starts = start_candidates + starts_from_end
         
         if all_starts and end_candidates:
             earliest_start = min(all_starts)
             latest_end = max(end_candidates)
             return int(max(0, latest_end - earliest_start))
             
    elif part_of_day == "Avond":
        # Evening: Span = (Latest End) - (Earliest Start)
        # Latest End comes from:
        # 1. Explicit end refs
        # 2. Derived ends from (Start + Duration)
        
        ends_from_start = []
        for p in protocols:
            s_m = _derive_start_time_minutes(p)
            dur_h = getattr(p, "visit_duration_hours", None)
            if s_m is not None and dur_h is not None:
                ends_from_start.append(int(s_m + int(dur_h * 60)))
                
        all_ends = end_candidates + ends_from_start
        
        if start_candidates and all_ends:
            earliest_start = min(start_candidates)
            latest_end = max(all_ends)
            return int(max(0, latest_end - earliest_start))
            
    # Fallback to max duration of any single protocol if complex span calculation fails
    return fallback_duration


def _derive_start_time_text_combined(
    protocols: list[Protocol], 
    part_of_day: str, 
    duration_minutes: int | None
) -> str | None:
    """Derive start time text using legacy logic (Earliest Start / Earliest End)."""
    # 0. Check for Absolute Time override
    # User Request: "Als dit protocol in een bucket zit met andere Avond bezoeken dan moet de absolute_time starttijd worden aangehouden."
    for p in protocols:
        if p.start_timing_reference == "ABSOLUTE_TIME" and p.start_time_absolute_from:
            return p.start_time_absolute_from.strftime("%H:%M")
            
    # Exception: Species 'HM' (Huiszwaluw/Huismus)
    if any(p.species.abbreviation == 'HM' for p in protocols):
        return "1-2 uur na zonsopkomst"

    # Exception: Paarverblijf + MV
    # "Avond" -> "Zonsopgang", "Ochtend" -> "3 uur voor zonsopgang"
    for p in protocols:
        if (
            p.function.name == "Paarverblijf"
            and (p.species.abbreviation == "MV" or p.species.name == "MV")
        ):
            if part_of_day == "Avond":
                return "Zonsondergang"
            if part_of_day == "Ochtend":
                return "3 uur voor zonsopgang"

    if part_of_day not in {"Ochtend", "Avond", "Dag"}:
        return _derive_start_time_text_for_visit(part_of_day, None)

    # 1. Gather candidates
    start_candidates = [
        _derive_start_time_minutes(p) for p in protocols 
        if _derive_start_time_minutes(p) is not None
    ]
    end_candidates = [
        _derive_end_time_minutes(p) for p in protocols
        if _derive_end_time_minutes(p) is not None
    ]
    
    local_minutes: int | None = None
    
    if part_of_day == "Ochtend":
         # Morning: 
         # 1. (Skipped: calc_start_for_duration logic from legacy, assuming standard duration fallback)
         # 2. Latest End - Duration (Recover Earliest Start from Span)
         if end_candidates and duration_minutes is not None:
             latest_end = max(end_candidates)
             local_minutes = int(latest_end - duration_minutes)
         # 3. Earliest Start
         elif start_candidates:
             local_minutes = int(min(start_candidates))
             
    elif part_of_day == "Dag":
        # Day: Usually defined by Start Time after Sunrise
        if start_candidates:
            # Earliest start time is the constraint
            local_minutes = int(min(start_candidates))
            
    else: # Avond
        # Evening:
        # 1. Earliest Start
        if start_candidates:
            local_minutes = int(min(start_candidates))
        # 2. Earliest End
        elif end_candidates:
            local_minutes = int(min(end_candidates))
            
    return _derive_start_time_text_for_visit(part_of_day, local_minutes)


def _derive_start_time_minutes(protocol: Protocol) -> int | None:
    """Return stored start_time_relative_minutes."""
    return protocol.start_time_relative_minutes


def _derive_end_time_minutes(protocol: Protocol) -> int | None:
    """Return end time in minutes (inverted relative value)."""
    rel = getattr(protocol, "end_time_relative_minutes", None)
    if rel is None:
        return None
    ref = getattr(protocol, "end_timing_reference", None)
    if ref == "SUNRISE":
        return -int(rel)
        
    return int(rel)


def _derive_start_time_text_for_visit(
    part_of_day: str | None, start_time_minutes: int | None
) -> str | None:
    """Format start time text (Dutch)."""
    if part_of_day == "Dag" and start_time_minutes is None:
        return "Overdag"
        
    if start_time_minutes is None:
        return None

    def fmt_hours(minutes: int) -> str:
        sign = -1 if minutes < 0 else 1
        m = abs(minutes)
        half_steps = round(m / 30)
        value_h = half_steps * 0.5
        text = f"{int(value_h)}" if value_h.is_integer() else f"{int(value_h)} ,5"
        text = text.replace(" ", "")
        return ("-" if sign < 0 else "") + text

    if part_of_day == "Ochtend":
        if start_time_minutes == 0:
            return "Zonsopkomst"
        hours = fmt_hours(start_time_minutes)
        direction = "na" if start_time_minutes > 0 else "voor"
        hours_clean = hours.lstrip("-").replace(".", ",")
        return f"{hours_clean} uur {direction} zonsopkomst"

    if part_of_day == "Avond":
        if start_time_minutes == 0:
            return "Zonsondergang"
        hours = fmt_hours(start_time_minutes)
        direction = "na" if start_time_minutes > 0 else "voor"
        hours_clean = hours.lstrip("-").replace(".", ",")
        return f"{hours_clean} uur {direction} zonsondergang"
        
    if part_of_day == "Dag":
        # Usually implies AFTER sunrise if we have minutes
        hours = fmt_hours(start_time_minutes)
        # Assuming Dag referencing Sunrise
        hours_clean = hours.lstrip("-").replace(".", ",")
        return f"{hours_clean} uur na zonsopkomst"

    return None


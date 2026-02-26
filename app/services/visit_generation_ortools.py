from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.utils import select_active

from app.models.cluster import Cluster
from app.models.protocol import Protocol
from app.models.visit import Visit
from app.models.user import User
from app.services.planning_run_errors import PlanningRunError
from app.services.visit_generation_common import (
    _generate_visit_requests,
    _build_compatibility_graph,
    _derive_part_options_base,
    _select_most_restrictive_precipitation,
    calculate_visit_props,
)

_logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class _VisitGenConfig:
    debug: bool
    debug_max_requests: int
    flex_target_window_days: int
    flex_deficit_weight: int
    early_weight: int
    relative_gap_limit: str | None
    time_limit_seconds: str | None
    period_mode: str
    period_miss_penalty: int
    short_crowding_weight: int


def _load_visit_gen_config() -> _VisitGenConfig:
    return _VisitGenConfig(
        debug=os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"},
        debug_max_requests=int(os.getenv("VISIT_GEN_DEBUG_MAX_REQUESTS", "50")),
        flex_target_window_days=int(
            os.getenv("VISIT_GEN_FLEX_TARGET_WINDOW_DAYS", "14")
        ),
        flex_deficit_weight=int(os.getenv("VISIT_GEN_FLEX_DEFICIT_WEIGHT", "200")),
        early_weight=int(os.getenv("VISIT_GEN_EARLY_WEIGHT", "0")),
        relative_gap_limit=os.getenv("VISIT_GEN_RELATIVE_GAP_LIMIT"),
        time_limit_seconds=os.getenv("VISIT_GEN_TIME_LIMIT_SECONDS"),
        period_mode=os.getenv("VISIT_GEN_PERIOD_MODE", "hard").strip().lower(),
        period_miss_penalty=int(os.getenv("VISIT_GEN_PERIOD_MISS_PENALTY", "500")),
        short_crowding_weight=int(os.getenv("VISIT_GEN_SHORT_CROWDING_WEIGHT", "0")),
    )


_CONFIG = _load_visit_gen_config()

_DEBUG_VISIT_GEN = _CONFIG.debug

_VISIT_GEN_FLEX_TARGET_WINDOW_DAYS = _CONFIG.flex_target_window_days
_VISIT_GEN_FLEX_DEFICIT_WEIGHT = _CONFIG.flex_deficit_weight
_VISIT_GEN_EARLY_WEIGHT = _CONFIG.early_weight
_VISIT_GEN_RELATIVE_GAP_LIMIT = _CONFIG.relative_gap_limit
_VISIT_GEN_TIME_LIMIT_SECONDS = _CONFIG.time_limit_seconds
_VISIT_GEN_PERIOD_MODE = _CONFIG.period_mode
_VISIT_GEN_PERIOD_MISS_PENALTY = _CONFIG.period_miss_penalty
_VISIT_GEN_SHORT_CROWDING_WEIGHT = _CONFIG.short_crowding_weight


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


def _generate_greedy_solution(
    requests: list,
) -> tuple[dict[int, int], dict[int, tuple[int, int]]]:
    """
    Generate a simple First-Fit greedy assignment of requests to visits.
    Returns: (assignment {request_index: visit_index}, bin_windows {visit_index: (start, end)})
    """
    # Sort requests to potentially improve packing (e.g. most constrained first?)
    # For now, just process in order or by ID.
    # Sorting by number of compatibility constraints (degree) might be better,
    # but simple First Fit is usually surprising good as a baseline.

    # Map visit_index -> list of assigned request indices
    bins: dict[int, list[int]] = {}
    assignment: dict[int, int] = {}

    # Track common constraints to prevent "Clique Failures"
    bin_parts: dict[int, set[str]] = {}
    bin_windows: dict[int, tuple[int, int]] = {}  # (start_ordinal, end_ordinal)

    all_parts = {"Ochtend", "Dag", "Avond"}

    # Sort requests by start date to align bins with time flow.
    # This reduces the chance of Predecessor Gap conflicts between bins.
    sorted_indices = sorted(
        range(len(requests)), key=lambda i: requests[i].window_from.toordinal()
    )

    for r_idx in sorted_indices:
        r = requests[r_idx]
        r_parts = (
            r.part_of_day_options if r.part_of_day_options is not None else all_parts
        )
        r_start = r.window_from.toordinal()
        r_end = r.window_to.toordinal()

        best_v_idx: int | None = None
        best_overlap_len: int = -1
        best_parts: set[str] | None = None
        best_window: tuple[int, int] | None = None

        # Try to fit in existing bins
        for v_idx, existing_r_idxs in bins.items():
            # 1. Check Common Part Intersection
            current_bin_parts = bin_parts[v_idx]
            intersection_parts = current_bin_parts.intersection(r_parts)
            if not intersection_parts:
                continue

            # 2. Check Common Window Intersection
            # (must overlap by at least MIN_EFFECTIVE_WINDOW_DAYS, or at least be valid)
            # The solver penalizes short windows < 7 days.
            # Compatibility usually requires roughly 10 days overlap.
            # Let's enforce a safe positive overlap to ensure validity.

            b_start, b_end = bin_windows[v_idx]
            common_start = max(b_start, r_start)
            common_end = min(b_end, r_end)

            # Enforce at least 1 day of overlap to be physically possible
            # Ideally enforce MIN_EFFECTIVE_WINDOW_DAYS (10) to match graph strictness
            if (
                common_end - common_start
            ) < 7:  # Use 7 as safe "not penalized" lower bound
                continue

            # 3. Check compatibility with ALL requests currently in this bin
            compatible_with_all = True
            for existing_idx in existing_r_idxs:
                existing_req = requests[existing_idx]
                if existing_req.id not in r.compatible_request_ids:
                    compatible_with_all = False
                    break

            if compatible_with_all:
                overlap_len = int(common_end - common_start)
                if overlap_len > best_overlap_len:
                    best_overlap_len = overlap_len
                    best_v_idx = v_idx
                    best_parts = intersection_parts
                    best_window = (common_start, common_end)

        if (
            best_v_idx is not None
            and best_parts is not None
            and best_window is not None
        ):
            bins[best_v_idx].append(r_idx)
            assignment[r_idx] = best_v_idx
            bin_parts[best_v_idx] = best_parts
            bin_windows[best_v_idx] = best_window
        else:
            # Create new bin
            new_v_idx = len(bins)
            bins[new_v_idx] = [r_idx]
            assignment[r_idx] = new_v_idx
            bin_parts[new_v_idx] = r_parts
            bin_windows[new_v_idx] = (r_start, r_end)

    return assignment, bin_windows


def _add_assignment_activation_and_symmetry_constraints(
    *,
    model: cp_model.CpModel,
    requests: list[Any],
    max_visits: int,
    req_to_visit: dict[tuple[int, int], cp_model.BoolVarT],
    visit_active: list[cp_model.BoolVarT],
) -> None:
    for r_idx, _ in enumerate(requests):
        model.Add(sum(req_to_visit[(r_idx, v)] for v in range(max_visits)) == 1)

    for v in range(max_visits):
        model.AddMaxEquality(
            visit_active[v],
            [req_to_visit[(r_idx, v)] for r_idx in range(len(requests))],
        )

    for v in range(max_visits - 1):
        model.Add(visit_active[v] >= visit_active[v + 1])


def _add_per_request_constraints(
    *,
    model: cp_model.CpModel,
    requests: list[Any],
    max_visits: int,
    req_to_visit: dict[tuple[int, int], cp_model.BoolVarT],
    visit_start: list[cp_model.IntVar],
    visit_part: list[cp_model.IntVar],
    req_start: list[cp_model.IntVar],
    req_window_lb: list[cp_model.IntVar],
    visit_window_start: list[cp_model.IntVar],
    min_date_ord: int,
    max_date_ord: int,
) -> list[cp_model.IntVar]:
    part_map = {"Ochtend": 0, "Dag": 1, "Avond": 2}
    req_parts: list[cp_model.IntVar] = []

    for r_idx, req in enumerate(requests):
        for v in range(max_visits):
            model.Add(req_start[r_idx] == visit_start[v]).OnlyEnforceIf(
                req_to_visit[(r_idx, v)]
            )

        earliest = (
            req.effective_window_from.toordinal()
            if getattr(req, "effective_window_from", None) is not None
            else req.window_from.toordinal()
        )
        model.Add(req_start[r_idx] >= earliest)
        model.Add(req_start[r_idx] <= req.window_to.toordinal())

        if req.predecessor:
            pred_id, gap_days = req.predecessor
            pred_idx = next(
                (i for i, r in enumerate(requests) if r.id == pred_id), None
            )
            if pred_idx is not None:
                pred_group_start = model.NewIntVar(
                    min_date_ord,
                    max_date_ord,
                    f"pred_group_start_r{r_idx}",
                )
                for v in range(max_visits):
                    model.Add(pred_group_start == visit_window_start[v]).OnlyEnforceIf(
                        req_to_visit[(pred_idx, v)]
                    )

                pred_plus_gap = model.NewIntVar(
                    min_date_ord,
                    max_date_ord + 365,
                    f"pred_group_start_plus_gap_r{r_idx}",
                )
                model.Add(pred_plus_gap == pred_group_start + gap_days)
                model.AddMaxEquality(req_window_lb[r_idx], [earliest, pred_plus_gap])
            else:
                model.Add(req_window_lb[r_idx] == earliest)
        else:
            model.Add(req_window_lb[r_idx] == earliest)

        for r2_idx in range(r_idx + 1, len(requests)):
            r2 = requests[r2_idx]
            if r2.id not in req.compatible_request_ids:
                for v in range(max_visits):
                    model.AddBoolOr(
                        [
                            req_to_visit[(r_idx, v)].Not(),
                            req_to_visit[(r2_idx, v)].Not(),
                        ]
                    )

        if req.predecessor:
            pred_id, gap_days = req.predecessor
            pred_idx = next(
                (i for i, r in enumerate(requests) if r.id == pred_id), None
            )
            if pred_idx is not None:
                model.Add(req_start[r_idx] >= req_start[pred_idx] + gap_days)

        allowed_parts = req.part_of_day_options
        domain_vals: list[int]
        if allowed_parts:
            domain_vals = sorted([part_map[p] for p in allowed_parts if p in part_map])
        else:
            domain_vals = [0, 1, 2]

        rp = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(domain_vals), f"req_part_{r_idx}"
        )
        req_parts.append(rp)

        for v in range(max_visits):
            model.Add(visit_part[v] == rp).OnlyEnforceIf(req_to_visit[(r_idx, v)])

    return req_parts


def _add_global_constraints(
    *,
    model: cp_model.CpModel,
    requests: list[Any],
    req_parts: list[cp_model.IntVar],
    req_start: list[cp_model.IntVar],
    min_date_ord: int,
    period_miss_vars: list[cp_model.IntVar],
) -> None:
    requests_by_proto: dict[int, list[int]] = defaultdict(list)
    for r_idx, req in enumerate(requests):
        requests_by_proto[req.protocol.id].append(r_idx)

    for p_id, r_idxs in requests_by_proto.items():
        p = requests[r_idxs[0]].protocol

        req_morning = getattr(p, "requires_morning_visit", False)
        req_evening = getattr(p, "requires_evening_visit", False)

        if req_morning:
            bools = []
            for rx in r_idxs:
                b = model.NewBoolVar(f"p{p_id}_r{rx}_is_morning")
                model.Add(req_parts[rx] == 0).OnlyEnforceIf(b)
                model.Add(req_parts[rx] != 0).OnlyEnforceIf(b.Not())
                bools.append(b)
            model.Add(sum(bools) >= 1)

        if req_evening:
            bools = []
            for rx in r_idxs:
                b = model.NewBoolVar(f"p{p_id}_r{rx}_is_evening")
                model.Add(req_parts[rx] == 2).OnlyEnforceIf(b)
                model.Add(req_parts[rx] != 2).OnlyEnforceIf(b.Not())
                bools.append(b)
            model.Add(sum(bools) >= 1)

        req_june = getattr(p, "requires_june_visit", False)
        req_july = getattr(p, "requires_july_visit", False)
        req_maternity = getattr(p, "requires_maternity_period_visit", False)

        if req_june or req_july or req_maternity:
            year = date.fromordinal(min_date_ord).year

            def _add_period_requirement(
                *,
                enabled: bool,
                label: str,
                valid_ords: set[int],
            ) -> None:
                if not enabled:
                    return

                domain_obj = cp_model.Domain.FromValues(sorted(list(valid_ords)))
                bools = []
                for rx in r_idxs:
                    b = model.NewBoolVar(f"p{p_id}_r{rx}_{label}")
                    model.AddLinearExpressionInDomain(
                        req_start[rx], domain_obj
                    ).OnlyEnforceIf(b)
                    bools.append(b)

                if _VISIT_GEN_PERIOD_MODE == "soft":
                    miss = model.NewBoolVar(f"p{p_id}_{label}_miss")
                    model.Add(sum(bools) == 0).OnlyEnforceIf(miss)
                    model.Add(sum(bools) >= 1).OnlyEnforceIf(miss.Not())
                    period_miss_vars.append(miss)
                else:
                    model.Add(sum(bools) >= 1)

            _add_period_requirement(
                enabled=req_june,
                label="june",
                valid_ords=set(_get_june_ordinals(year)),
            )
            _add_period_requirement(
                enabled=req_july,
                label="july",
                valid_ords=set(_get_july_ordinals(year)),
            )
            _add_period_requirement(
                enabled=req_maternity,
                label="maternity",
                valid_ords=set(_get_maternity_ordinals(year)),
            )


def _add_visit_window_and_shortness_constraints(
    *,
    model: cp_model.CpModel,
    requests: list[Any],
    max_visits: int,
    req_to_visit: dict[tuple[int, int], cp_model.BoolVarT],
    visit_active: list[cp_model.BoolVarT],
    req_window_lb: list[cp_model.IntVar],
    visit_end: list[cp_model.IntVar],
    visit_window_start: list[cp_model.IntVar],
    min_date_ord: int,
    max_date_ord: int,
) -> tuple[list[cp_model.BoolVarT], list[cp_model.IntVar], list[cp_model.IntVar]]:
    is_short = [model.NewBoolVar(f"visit_is_short_{v}") for v in range(max_visits)]
    flex_deficit = [
        model.NewIntVar(0, _VISIT_GEN_FLEX_TARGET_WINDOW_DAYS, f"flex_deficit_{v}")
        for v in range(max_visits)
    ]

    short_crowding_terms: list[cp_model.IntVar] = []

    infinity_ord = max_date_ord + 100

    for v in range(max_visits):
        ends_in_visit = []
        for r_idx, req in enumerate(requests):
            eff = model.NewIntVar(min_date_ord, infinity_ord, f"eff_end_r{r_idx}_v{v}")
            model.Add(eff == req.window_to.toordinal()).OnlyEnforceIf(
                req_to_visit[(r_idx, v)]
            )
            model.Add(eff == infinity_ord).OnlyEnforceIf(req_to_visit[(r_idx, v)].Not())
            ends_in_visit.append(eff)

        model.AddMinEquality(visit_end[v], ends_in_visit)

        starts_in_visit = []
        for r_idx, _req in enumerate(requests):
            eff = model.NewIntVar(
                min_date_ord,
                max_date_ord,
                f"eff_start_r{r_idx}_v{v}",
            )
            model.Add(eff == req_window_lb[r_idx]).OnlyEnforceIf(
                req_to_visit[(r_idx, v)]
            )
            model.Add(eff == min_date_ord).OnlyEnforceIf(req_to_visit[(r_idx, v)].Not())
            starts_in_visit.append(eff)

        model.AddMaxEquality(visit_window_start[v], starts_in_visit)

        model.Add(is_short[v] == 0).OnlyEnforceIf(visit_active[v].Not())

        duration = model.NewIntVar(-365, 3650, f"duration_{v}")
        model.Add(duration == visit_end[v] - visit_window_start[v])

        model.Add(duration < 7).OnlyEnforceIf([visit_active[v], is_short[v]])
        model.Add(duration >= 7).OnlyEnforceIf([visit_active[v], is_short[v].Not()])

        if _VISIT_GEN_SHORT_CROWDING_WEIGHT:
            for r_idx in range(len(requests)):
                in_short = model.NewBoolVar(f"r{r_idx}_in_short_v{v}")
                model.Add(in_short <= req_to_visit[(r_idx, v)])
                model.Add(in_short <= is_short[v])
                model.Add(in_short >= req_to_visit[(r_idx, v)] + is_short[v] - 1)
                short_crowding_terms.append(in_short)

        deficit_raw = model.NewIntVar(
            -3650,
            _VISIT_GEN_FLEX_TARGET_WINDOW_DAYS,
            f"flex_deficit_raw_{v}",
        )
        model.Add(deficit_raw == _VISIT_GEN_FLEX_TARGET_WINDOW_DAYS - duration)
        model.AddMaxEquality(flex_deficit[v], [0, deficit_raw])

    return is_short, flex_deficit, short_crowding_terms


async def generate_visits_cp_sat(
    db: AsyncSession,
    cluster: Cluster,
    protocols: list[Protocol],
    *,
    default_required_researchers: int | None = None,
    default_planned_week: int | None = None,
    default_researcher_ids: list[int] | None = None,
    default_planning_locked: bool = False,
    default_expertise_level: str | None = None,
    default_wbc: bool = False,
    default_fiets: bool = False,
    default_vog: bool = False,
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

        if len(requests) <= _CONFIG.debug_max_requests:
            for r in requests:
                earliest = (
                    r.effective_window_from
                    if getattr(r, "effective_window_from", None) is not None
                    else r.window_from
                )
                pred_str = (
                    f"{r.predecessor[0]}+{r.predecessor[1]}"
                    if getattr(r, "predecessor", None)
                    else "-"
                )
                _logger.info(
                    "REQ: %s proto=%s v_idx=%s win=[%s..%s] eff_from=%s pred=%s parts=%s",
                    r.id,
                    r.protocol.id,
                    getattr(r, "visit_index", None),
                    r.window_from,
                    r.window_to,
                    earliest,
                    pred_str,
                    sorted(list(r.part_of_day_options or [])),
                )

    # 2. Model Construction
    model = cp_model.CpModel()
    max_visits = len(requests)

    # --- Heuristic Hint Injection ---
    # To avoid "FEASIBLE" but poor solutions (e.g. 1 visit per request), we calculate
    # a greedy First-Fit solution and provide it as a hint to the solver.
    # This helps the solver start from a "Reasonable" neighborhood.

    greedy_assignment, bin_windows = _generate_greedy_solution(requests)

    if _DEBUG_VISIT_GEN:
        used_visits = len(set(greedy_assignment.values()))
        _logger.info(
            "GREEDY: Found initial solution with %d visits (Hinting Solver)",
            used_visits,
        )

        # DEBUG: Log distribution of requests in greedy bins
        bins_debug = defaultdict(list)
        for r_idx, v_idx in greedy_assignment.items():
            bins_debug[v_idx].append(r_idx)

        for v_idx, r_list in sorted(bins_debug.items())[:5]:  # Log first 5 bins
            p_ids = [requests[r].protocol.id for r in r_list]
            _logger.info(
                "  Bucket %d has %d requests: Protos %s", v_idx, len(r_list), p_ids
            )
    # --------------------------------

    # Variables
    visit_active = [model.NewBoolVar(f"visit_active_{v}") for v in range(max_visits)]

    period_miss_vars: list[cp_model.IntVar] = []

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

    visit_start = [
        model.NewIntVar(min_date_ord, max_date_ord, f"visit_start_{v}")
        for v in range(max_visits)
    ]
    visit_part = [
        model.NewIntVar(0, 2, f"visit_part_{v}") for v in range(max_visits)
    ]  # 0=Ochtend, 1=Dag, 2=Avond
    req_start = [
        model.NewIntVar(min_date_ord, max_date_ord, f"req_start_{r_idx}")
        for r_idx in range(len(requests))
    ]

    req_window_lb = [
        model.NewIntVar(min_date_ord, max_date_ord + 365, f"req_window_lb_{r_idx}")
        for r_idx in range(len(requests))
    ]

    visit_end = [
        model.NewIntVar(min_date_ord, max_date_ord + 365, f"visit_end_{v}")
        for v in range(max_visits)
    ]

    visit_window_start = [
        model.NewIntVar(min_date_ord, max_date_ord, f"visit_window_start_{v}")
        for v in range(max_visits)
    ]

    # C1. Every request must be assigned to EXACTLY one visit
    # C2. Visit Activation: If any request is in visit v, visit v is active
    # C3. Symmetry Breaking (Sort visits by active status to push empty visits to end)
    _add_assignment_activation_and_symmetry_constraints(
        model=model,
        requests=requests,
        max_visits=max_visits,
        req_to_visit=req_to_visit,
        visit_active=visit_active,
    )

    # C4. Validity Constraints per Request
    req_parts = _add_per_request_constraints(
        model=model,
        requests=requests,
        max_visits=max_visits,
        req_to_visit=req_to_visit,
        visit_start=visit_start,
        visit_part=visit_part,
        req_start=req_start,
        req_window_lb=req_window_lb,
        visit_window_start=visit_window_start,
        min_date_ord=min_date_ord,
        max_date_ord=max_date_ord,
    )

    # C6. "At Least One" Global Constraints
    _add_global_constraints(
        model=model,
        requests=requests,
        req_parts=req_parts,
        req_start=req_start,
        min_date_ord=min_date_ord,
        period_miss_vars=period_miss_vars,
    )

    # C7. Penalize "Tight" Windows (Short Effective Duration)
    # User discourages planning resulting in effective windows < 7 days.
    # We apply a penalty if (visit_end - visit_start) < 7 days, forcing the solver to prefer
    # adding another visit over squeezing protocols into a tight window.
    is_short, flex_deficit, short_crowding_terms = (
        _add_visit_window_and_shortness_constraints(
            model=model,
            requests=requests,
            max_visits=max_visits,
            req_to_visit=req_to_visit,
            visit_active=visit_active,
            req_window_lb=req_window_lb,
            visit_end=visit_end,
            visit_window_start=visit_window_start,
            min_date_ord=min_date_ord,
            max_date_ord=max_date_ord,
        )
    )

    # Objective Function
    M = (max_date_ord - min_date_ord) * len(requests) * 2 + 1000
    SHORT_PENALTY = M + 500  # Cost higher than adding a new visit (M)

    if _VISIT_GEN_PERIOD_MODE not in {"hard", "soft"}:
        raise ValueError(
            "VISIT_GEN_PERIOD_MODE must be 'hard' or 'soft' (got "
            f"{_VISIT_GEN_PERIOD_MODE!r})"
        )

    # Priority:
    # 1. Minimize total Visits (M)
    # 2. Avoid Short Windows (SHORT_PENALTY)
    # 3. Prefer Morning Requests (Weight 2)
    # 4. Compactness / Early Starts (Weight 1)
    # 5. Prefer Morning Visits (Tie-break weight 1)

    model.Minimize(
        sum(visit_active[v] * M for v in range(max_visits))
        + sum(is_short[v] * SHORT_PENALTY for v in range(max_visits))
        + (_VISIT_GEN_FLEX_DEFICIT_WEIGHT * sum(flex_deficit))
        + (_VISIT_GEN_PERIOD_MISS_PENALTY * sum(period_miss_vars))
        + (
            (_VISIT_GEN_SHORT_CROWDING_WEIGHT * sum(short_crowding_terms))
            if _VISIT_GEN_SHORT_CROWDING_WEIGHT
            else 0
        )
        +
        # Preference Logic:
        # Default: Prefer Morning (Minimizing rp*2 -> 0 is best)
        # Paarverblijf: Prefer Evening (Minimizing (2-rp)*2 -> 2 is best)
        sum(
            (
                (2 - req_parts[i]) * 2
                if getattr(getattr(requests[i].protocol, "function", None), "name", "")
                == "Paarverblijf"
                else req_parts[i] * 2
            )
            for i in range(len(req_parts))
        )
        + (
            _VISIT_GEN_EARLY_WEIGHT
            * sum((req_start[i] - min_date_ord) for i in range(len(req_start)))
        )
        + sum(visit_part)
    )

    # Solve
    solver = cp_model.CpSolver()

    # Dynamic Time Limit: Scale with complexity (number of requests)
    # Base 30s + 0.5s per request. For 75 requests -> ~50s. For 500 -> 250s.
    # We can be more aggressive now that we have the Greedy Hint to prevent disaster cases.
    time_limit = max(15.0, min(60.0, len(requests) * 0.6))
    if _VISIT_GEN_TIME_LIMIT_SECONDS:
        time_limit = float(_VISIT_GEN_TIME_LIMIT_SECONDS)
    solver.parameters.max_time_in_seconds = time_limit

    # Disable parallelism to prevent OOM on single-core/low-memory servers
    # The heuristic hint is sufficient to guide the search without needing portfolio search.
    solver.parameters.num_search_workers = 2

    try:
        if _VISIT_GEN_RELATIVE_GAP_LIMIT:
            solver.parameters.relative_gap_limit = float(_VISIT_GEN_RELATIVE_GAP_LIMIT)
    except AttributeError:
        pass

    if _DEBUG_VISIT_GEN:
        used_visits = len(set(greedy_assignment.values()))
        _logger.info(
            "GREEDY: Found initial solution with %d visits (Hinting Solver)",
            used_visits,
        )

        # DEBUG: Log distribution of requests in greedy bins
        bins_debug = defaultdict(list)
        for r_idx, v_idx in greedy_assignment.items():
            bins_debug[v_idx].append(r_idx)

        for v_idx, r_list in sorted(bins_debug.items())[:5]:  # Log first 5 bins
            p_ids = [requests[r].protocol.id for r in r_list]
            win = bin_windows.get(v_idx)
            win_str = (
                f"{date.fromordinal(win[0])} to {date.fromordinal(win[1])}"
                if win
                else "N/A"
            )
            _logger.info(
                "  Bucket %d: %d reqs, Window [%s], Protos %s",
                v_idx,
                len(r_list),
                win_str,
                p_ids,
            )
        _logger.info(
            "Solver Time Limit set to %.1fs for %d requests", time_limit, len(requests)
        )

    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        active_count = sum(
            1 for v in range(max_visits) if solver.BooleanValue(visit_active[v])
        )
        obj = solver.ObjectiveValue()
        bound = solver.BestObjectiveBound()
        denom = max(1.0, abs(obj))
        gap = max(0.0, (obj - bound) / denom)

        if status == cp_model.OPTIMAL:
            quality = "OPTIMAL"
        elif gap <= 0.01:
            quality = "EXCELLENT"
        elif gap <= 0.05:
            quality = "GOOD"
        elif gap <= 0.3:
            quality = "OK"
        else:
            quality = "WEAK"

        time_limit_reached = solver.WallTime() >= (time_limit * 0.99)
        _logger.info(
            "VisitGen CP-SAT: status=%s time=%.2fs limit=%.1fs requests=%d active_visits=%d obj=%.2f bound=%.2f gap=%.4f conflicts=%d branches=%d",
            solver.StatusName(status),
            solver.WallTime(),
            time_limit,
            len(requests),
            active_count,
            obj,
            bound,
            gap,
            solver.NumConflicts(),
            solver.NumBranches(),
        )
        _logger.info(
            "VisitGen CP-SAT summary: quality=%s gap=%.4f time_limit_reached=%s",
            quality,
            gap,
            time_limit_reached,
        )
    else:
        _logger.info(
            "VisitGen CP-SAT: status=%s time=%.2fs limit=%.1fs requests=%d conflicts=%d branches=%d",
            solver.StatusName(status),
            solver.WallTime(),
            time_limit,
            len(requests),
            solver.NumConflicts(),
            solver.NumBranches(),
        )
        _logger.info("VisitGen CP-SAT summary: quality=FAILED")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        msg = f"VisitGen CP-SAT produced no feasible solution. Status={solver.StatusName(status)}"
        _logger.warning(msg)
        raise PlanningRunError(msg, technical_detail=msg)

    if quality == "WEAK" and time_limit_reached:
        msg = (
            "VisitGen CP-SAT solution rejected: quality=WEAK and time limit reached "
            f"(status={solver.StatusName(status)} gap={gap:.4f} limit={time_limit:.1f}s time={solver.WallTime():.2f}s)"
        )
        _logger.warning(msg)
        raise PlanningRunError(msg, technical_detail=msg)

    if _DEBUG_VISIT_GEN:
        _logger.info(
            "CP-SAT Solved: Status=%s Val=%s",
            solver.StatusName(status),
            solver.ObjectiveValue(),
        )

        total_deficit = 0
        total_duration = 0
        active_visits = 0

        for v in range(max_visits):
            if not solver.BooleanValue(visit_active[v]):
                continue
            active_visits += 1

            start_ord = solver.Value(visit_start[v])
            end_ord = solver.Value(visit_end[v])
            window_start_ord = solver.Value(visit_window_start[v])
            dur = int(end_ord - window_start_ord)
            deficit = int(max(0, _VISIT_GEN_FLEX_TARGET_WINDOW_DAYS - dur))
            total_deficit += deficit
            total_duration += dur

            assigned_req_indices = [
                i
                for i in range(len(requests))
                if solver.BooleanValue(req_to_visit[(i, v)])
            ]
            assigned_req_ids = [requests[i].id for i in assigned_req_indices]
            assigned_proto_ids = [requests[i].protocol.id for i in assigned_req_indices]

            _logger.info(
                "VisitGen CP-SAT visit v=%d window_start=%s exec_start=%s end=%s duration_days=%d flex_deficit=%d reqs=%s",
                v,
                date.fromordinal(window_start_ord),
                date.fromordinal(start_ord),
                date.fromordinal(end_ord),
                dur,
                deficit,
                assigned_req_ids,
            )

            _logger.info(
                "VisitGen CP-SAT visit v=%d protos=%s",
                v,
                assigned_proto_ids,
            )

        _logger.info(
            "VisitGen CP-SAT flex summary: active_visits=%d target_days=%d deficit_weight=%d early_weight=%d total_deficit=%d total_duration=%d",
            active_visits,
            _VISIT_GEN_FLEX_TARGET_WINDOW_DAYS,
            _VISIT_GEN_FLEX_DEFICIT_WEIGHT,
            _VISIT_GEN_EARLY_WEIGHT,
            total_deficit,
            total_duration,
        )

    # Reconstruct Visits
    visits: list[Visit] = []
    inv_part_map = {0: "Ochtend", 1: "Dag", 2: "Avond"}
    pvw_by_id = {
        w.id: w for p in protocols for w in (p.visit_windows or []) if w.id is not None
    }

    for v in range(max_visits):
        if not solver.BooleanValue(visit_active[v]):
            continue

        window_start_ord = solver.Value(visit_window_start[v])
        part_idx = solver.Value(visit_part[v])
        visit_date = date.fromordinal(window_start_ord)
        part_str = inv_part_map.get(part_idx)

        assigned_req_indices = [
            i for i in range(len(requests)) if solver.BooleanValue(req_to_visit[(i, v)])
        ]
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
        new_visit.planned_week = default_planned_week
        new_visit.planning_locked = default_planning_locked
        new_visit.expertise_level = default_expertise_level
        new_visit.wbc = default_wbc
        new_visit.fiets = default_fiets
        new_visit.vog = default_vog
        new_visit.hub = default_hub
        new_visit.dvp = default_dvp
        new_visit.sleutel = default_sleutel

        if default_researcher_ids:
            stmt_users = select_active(User).where(User.id.in_(default_researcher_ids))
            new_visit.researchers = (
                (await db.execute(stmt_users)).scalars().unique().all()
            )

        # Attach protocols and related entities
        unique_protos = list(
            {r.protocol.id: r.protocol for r in assigned_reqs}.values()
        )
        new_visit.functions = list(
            {p.function.id: p.function for p in unique_protos if p.function}.values()
        )
        new_visit.species = list(
            {p.species.id: p.species for p in unique_protos if p.species}.values()
        )
        visit_pvws = [
            pvw_by_id[r.pvw_id] for r in assigned_reqs if r.pvw_id in pvw_by_id
        ]
        if visit_pvws:
            new_visit.protocol_visit_windows = list(
                {pvw.id: pvw for pvw in visit_pvws}.values()
            )

        # Calculate duration/text
        try:
            ref_date = (
                min(r.window_from for r in assigned_reqs)
                if assigned_reqs
                else visit_date
            )
            v_indices = {r.protocol.id: r.visit_index for r in assigned_reqs}

            dur, txt, rem = calculate_visit_props(
                unique_protos,
                part_str,
                reference_date=ref_date,
                visit_indices=v_indices,
            )
            new_visit.duration = dur
            new_visit.start_time_text = txt
            if rem:
                if new_visit.remarks_field:
                    new_visit.remarks_field += "\n" + rem
                else:
                    new_visit.remarks_field = rem
        except ImportError:
            pass

        # Weather Constraints
        min_temp = max(
            (
                p.min_temperature_celsius
                for p in unique_protos
                if p.min_temperature_celsius is not None
            ),
            default=None,
        )
        max_wind = min(
            (
                p.max_wind_force_bft
                for p in unique_protos
                if p.max_wind_force_bft is not None
            ),
            default=None,
        )
        precip_options = [
            p.max_precipitation for p in unique_protos if p.max_precipitation
        ]
        precip = _select_most_restrictive_precipitation(precip_options)

        new_visit.min_temperature_celsius = min_temp
        new_visit.max_wind_force_bft = max_wind
        new_visit.max_precipitation = precip

        # Generate Remarks Field
        remarks_lines = []

        def _is_vleermuis(proto: Protocol) -> bool:
            fam_name = getattr(
                getattr(getattr(proto, "species", None), "family", None), "name", ""
            )
            return fam_name == "Vleermuis"

        def _species_label(proto: Protocol) -> str | None:
            sp = getattr(proto, "species", None)
            if not sp:
                return None
            return getattr(sp, "abbreviation", None) or getattr(sp, "name", None)

        def _format_species_list(items: list[str]) -> str:
            if len(items) == 1:
                return items[0]
            if len(items) == 2:
                return f"{items[0]} en {items[1]}"
            return ", ".join(items[:-1]) + f", en {items[-1]}"

        visit_species = {_species_label(p) for p in unique_protos}
        visit_species.discard(None)
        visit_species_set = {str(x) for x in visit_species}

        lv_protocols = [
            p
            for p in unique_protos
            if _is_vleermuis(p)
            and getattr(getattr(p, "species", None), "abbreviation", None) == "LV"
        ]
        lv_function_ids = {
            p.function_id for p in lv_protocols if p.function_id is not None
        }
        lv_evening_only = any(
            getattr(p, "end_time_relative_minutes", None) is None for p in lv_protocols
        )

        morning_required_function_names = {"Kraamverblijfplaats", "Zomerverblijfplaats"}
        if part_str == "Avond" and lv_protocols and lv_evening_only and lv_function_ids:
            candidate_species: set[str] = set()
            for p in protocols:
                if not _is_vleermuis(p):
                    continue
                if p.function_id not in lv_function_ids:
                    continue
                if getattr(getattr(p, "species", None), "abbreviation", None) == "LV":
                    continue

                func_name = getattr(getattr(p, "function", None), "name", "") or ""
                requires_morning = bool(getattr(p, "requires_morning_visit", False))
                if not (
                    requires_morning or func_name in morning_required_function_names
                ):
                    continue

                label = _species_label(p)
                if label:
                    candidate_species.add(label)

            missing = sorted(candidate_species.difference(visit_species_set))
            if missing:
                remarks_lines.append(
                    f"Ook graag soorten {_format_species_list(missing)} onderzoeken"
                )

        # Special Case: Rugstreeppad using specific function
        has_rugstreeppad_platen = False
        for r in assigned_reqs:
            p = r.protocol
            s_name = getattr(getattr(p, "species", None), "name", "")
            f_name = getattr(getattr(p, "function", None), "name", "")
            if (
                s_name == "Rugstreeppad"
                and f_name == "platen neerleggen, eisnoeren/larven"
            ):
                has_rugstreeppad_platen = True
                break

        if has_rugstreeppad_platen:
            remarks_lines.append(
                "Fijnmazig schepnet (RAVON-type) mee. Ook letten op koren en aanwezige individuen. Platen neerleggen in plangebied. Vuistregel circa 10 platen per 100m geschikt leefgebied."
            )

        # Special Case: Vlinder Family
        has_vlinder = False
        for r in assigned_reqs:
            p = r.protocol
            fam_name = getattr(
                getattr(getattr(p, "species", None), "family", None), "name", ""
            )
            if fam_name == "Vlinder":
                has_vlinder = True
                break

        if has_vlinder:
            remarks_lines.append(
                "Min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (met meer >50% bewolking)"
            )

        # Special Case: Langoren Family
        has_langoren = False
        for r in assigned_reqs:
            p = r.protocol
            fam_name = getattr(
                getattr(getattr(p, "species", None), "family", None), "name", ""
            )
            if fam_name == "Langoren":
                has_langoren = True
                break

        if has_langoren:
            remarks_lines.append("Geen mist, sneeuwval. Bodemtemperatuur < 15 graden")

        # Special Case: Vleermuis & Zwaluw (GZ) Combine
        has_vleermuis_any = any(_is_vleermuis(r.protocol) for r in assigned_reqs)
        has_zwaluw_gz = False
        for r in assigned_reqs:
            p = r.protocol
            fam_name = getattr(
                getattr(getattr(p, "species", None), "family", None), "name", ""
            )
            sp_abbr = getattr(getattr(p, "species", None), "abbreviation", "")
            if fam_name == "Zwaluw" and sp_abbr == "GZ":
                has_zwaluw_gz = True
                break

        if has_vleermuis_any and has_zwaluw_gz:
            remarks_lines.append(
                "1 persoon voor GZ-gedeelte, zelf overleggen wie. De andere(n) begint bij zonsondergang."
            )

        # Special Case: SMP Zwaluw
        has_smp_zwaluw = False
        for r in assigned_reqs:
            p = r.protocol
            fam_name = getattr(
                getattr(getattr(p, "species", None), "family", None), "name", ""
            )
            func_name = getattr(getattr(p, "function", None), "name", "") or ""
            if fam_name == "Zwaluw" and func_name.startswith("SMP"):
                has_smp_zwaluw = True
                break

        if has_smp_zwaluw:
            remarks_lines.append(
                """Minimum temperatuur:
25 Mei - 31 Mei: 17
1 Jun - 7 Jun: 18
8 Jun - 14 Jun: 19
15 Jun - 21 Jun: 19.5
22 Jun - 28 Jun: 20
29 Jun - 5 Jul: 20
6 Jul - 12 Jul: 20
13 Jul - 19 Jul: 20"""
            )

        if remarks_lines:
            if new_visit.remarks_field:
                new_visit.remarks_field += "\n" + "\n".join(remarks_lines)
            else:
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
    stmt = select_active(Visit).where(Visit.cluster_id == cluster.id)
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

        if _DEBUG_VISIT_GEN and i >= len(existing_visits):  # Log new ones
            _logger.info(
                "  -> Created Visit %d: %s %s (%s)",
                v.visit_nr,
                v.from_date,
                v.part_of_day,
                v.remarks_field,
            )

    return visits, warnings

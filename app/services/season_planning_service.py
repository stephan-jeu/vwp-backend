from __future__ import annotations

import os
import math
from datetime import date, timedelta
from typing import NamedTuple

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.visit import Visit
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.species import Species
from app.models.user import User
from app.models.availability import AvailabilityWeek
from app.services.visit_planning_selection import (
    _first_function_name,
    _any_function_contains,
)
from app.schemas.capacity import CapacitySimulationResponse
from ortools.sat.python import cp_model


_DEBUG_SEASON_PLANNING = os.getenv("SEASON_PLANNING_DEBUG", "").lower() in (
    "true",
    "1",
    "yes",
)

_DEBUG_SEASON_PLANNING_VISIT_ID_RAW = os.getenv("SEASON_PLANNING_DEBUG_VISIT_ID")
try:
    _DEBUG_SEASON_PLANNING_VISIT_ID = (
        int(_DEBUG_SEASON_PLANNING_VISIT_ID_RAW)
        if _DEBUG_SEASON_PLANNING_VISIT_ID_RAW
        else None
    )
except ValueError:
    _DEBUG_SEASON_PLANNING_VISIT_ID = None


class CapacityProfile(NamedTuple):
    """
    Represents a unique set of skills/capacities (e.g. "Bat Expert + Bird Expert").
    Users are grouped into these profiles to reduce solver variables.
    """

    id: int
    name: str  # e.g. "Pool A"
    skills: tuple[str, ...]  # ("Vleermuis", "Zwaluw")
    total_weekly_tokens: dict[int, int]  # WeekNum -> Total Capacity


class SeasonPlanningService:
    @staticmethod
    def _get_contract_value(u: User) -> str:
        """Return the user's contract type as a normalized lowercase string.

        Args:
            u: User model instance.

        Returns:
            The contract type value as lowercase (e.g. "intern", "flex", "zzp").
        """

        raw = getattr(u, "contract", None)
        if isinstance(raw, str):
            return raw.lower()

        value = getattr(raw, "value", None)
        if isinstance(value, str):
            return value.lower()

        raw = getattr(u, "contract_type", None)
        if isinstance(raw, str):
            return raw.lower()

        value = getattr(raw, "value", None)
        if isinstance(value, str):
            return value.lower()

        return ""

    @staticmethod
    def _get_required_user_flag(v: Visit) -> str:
        """
        Duplicate of logic in capacity_simulation_service (refactor later).
        Determines the 'Skill' required for a visit.
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
                return f"SMP {fam_name.capitalize()}"

        # 2. VRFG Check
        if _any_function_contains(v, ("Vliegroute", "Foerageergebied")):
            return "VR/FG"

        # 3. Standard Family Fallback
        try:
            sp = (v.species or [None])[0]
            fam = getattr(sp, "family", None)
            name = getattr(fam, "name", None)
            if isinstance(name, str) and name.strip():
                raw = name.strip().lower()
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
                return raw.capitalize()
        except Exception:
            pass
        return "?"

    @staticmethod
    def _get_user_skill_keys(u: User) -> set[str]:
        """
        Determines the set of 'Skills' a user possesses.
        This roughly inverses _get_required_user_flag logic.
        """
        skills = set()

        # SMP
        if u.smp_vleermuis:
            skills.add("SMP Vleermuis")
        if u.smp_gierzwaluw:
            skills.add("SMP Gierzwaluw")
        if u.smp_huismus:
            skills.add("SMP Huismus")  # Covers smp_zangvogel/standard

        # Special
        if u.vrfg:
            skills.add("VR/FG")

        # Species Families (Exact mapping to _get_required_user_flag)
        if u.langoor:
            skills.add("Langoor")
        if u.schijfhoren:
            skills.add("Schijfhoren")
        if u.zwaluw:
            skills.add("Zwaluw")

        # Vlinder cluster
        # _get_required_user_flag maps "vlinder", "grote vos", "iepenpage" -> "Vlinder"
        # User has `vlinder` and `teunisbloempijlstaart`.
        if u.vlinder or u.teunisbloempijlstaart:
            skills.add("Vlinder")

        # General Families
        # User model has simple booleans for many families
        if u.vleermuis:
            skills.add("Vleermuis")
        if u.zangvogel:
            skills.add("Zangvogel")
        if u.roofvogel:
            skills.add("Roofvogel")
        if u.pad:
            skills.add("Pad")  # Maps to "Pad" (if family="pad")?
        if u.biggenkruid:
            skills.add("Biggenkruid")

        # Fallback for generic logic?
        # Ideally, we should unify this with the Qualification model, but
        # for now we hardcode the known flags.

        return skills

    @staticmethod
    async def run_season_solver(
        db: AsyncSession,
        start_date: date,
        *,
        include_quotes: bool = False,
        persist: bool = True,
    ) -> None:
        """Run the seasonal planner to assign provisional weeks.

        Args:
            db: Async SQLAlchemy session.
            start_date: Start date for the planning horizon.
            include_quotes: When True, include quote projects in the solver input.
            persist: When True, commit provisional week updates to the database.

        Returns:
            None.
        """
        # 1. Load Data
        visits = await SeasonPlanningService._load_all_active_visits(
            db, start_date, include_quotes=include_quotes
        )
        users = await SeasonPlanningService._load_all_users(db)

        # Load Availability: Map[User.id -> WeekNum -> DaysAvailable]
        avail_map = await SeasonPlanningService._load_availability_map(
            db, start_date.year
        )

        # 2. Run Logic
        SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

        # 3. Commit
        if persist:
            await db.commit()

    @staticmethod
    def solve_season(
        start_date: date,
        visits: list[Visit],
        users: list[User],
        avail_map: dict[tuple[int, int], AvailabilityWeek],
    ) -> None:
        """
        Pure logic solver for Season Planning.
        Updates visits in-place with provisional_week.
        """
        year = start_date.year
        current_week = start_date.isocalendar().week
        horizon_weeks = range(current_week, 54)

        custom_fixed_demand_by_week: dict[int, int] = {}
        custom_fixed_demand_by_week_daypart: dict[tuple[int, str], int] = {}
        for v in visits:
            is_custom = bool(
                getattr(v, "custom_function_name", None)
                or getattr(v, "custom_species_name", None)
            )
            if not is_custom:
                continue

            planned_week = getattr(v, "planned_week", None)
            provisional_week = getattr(v, "provisional_week", None)
            target_week = planned_week or provisional_week
            if not target_week:
                continue

            try:
                w_mon = date.fromisocalendar(year, int(target_week), 1)
                w_fri = w_mon + timedelta(days=4)
            except Exception:
                continue

            v_start = getattr(v, "from_date", None) or start_date
            v_end = getattr(v, "to_date", None) or date.max
            overlap_start = max(v_start, w_mon)
            overlap_end = min(v_end, w_fri)
            overlap_days = (overlap_end - overlap_start).days + 1
            if overlap_days < 1:
                continue

            researchers = getattr(v, "researchers", None)
            if researchers:
                cost = len(researchers)
            else:
                cost = getattr(v, "required_researchers", None) or 1
            window_weight = math.ceil(5 / overlap_days)
            part_of_day = (getattr(v, "part_of_day", None) or "").strip()
            part_key = {"Ochtend": "m", "Dag": "d", "Avond": "n"}.get(part_of_day)
            custom_fixed_demand_by_week[int(target_week)] = (
                custom_fixed_demand_by_week.get(int(target_week), 0)
                + cost * window_weight
            )
            if part_key is not None:
                custom_fixed_demand_by_week_daypart[(int(target_week), part_key)] = (
                    custom_fixed_demand_by_week_daypart.get(
                        (int(target_week), part_key),
                        0,
                    )
                    + cost * window_weight
                )

        # 2a. Supply: Build Capacity Supply Map (Skill -> Week -> TotalSlots)
        # First, map each user to their skills
        user_skills = {
            u.id: SeasonPlanningService._get_user_skill_keys(u) for u in users
        }

        # Initialize Supply
        # Structure: supply[skill][week] = int total_days
        supply = {}

        # 2b. extended Supply: Add 'Intern' and 'Supervisor' pseudo-skills
        # Map: supply['Intern'][w] = total_intern_days
        supply_intern = {}
        supply_supervisor = {}

        for u in users:
            contract = SeasonPlanningService._get_contract_value(u)
            exp = (getattr(u, "experience_bat", "") or "").lower()

            is_intern = contract == "intern"
            # specific definition for Supervisor: Senior OR (Intern AND Not Junior)
            is_supervisor = exp in {"senior", "medior"} or (
                contract == "intern" and exp != "junior"
            )

            # REMOVED FILTER: We need to process ALL users for generic supply!
            # if not (is_intern or is_supervisor):
            #     continue

            for w in horizon_weeks:
                # Availability
                aw = avail_map.get((u.id, w))
                total_days = (
                    (aw.morning_days or 0)
                    + (aw.daytime_days or 0)
                    + (aw.nighttime_days or 0)
                    + (aw.flex_days or 0)
                    if aw
                    else 0
                )

                if total_days > 0:
                    if _DEBUG_SEASON_PLANNING:
                        logger.debug(
                            "SeasonPlanning: user=%s week=%s days=%s",
                            u.id,
                            w,
                            total_days,
                        )
                    # Generic Skills
                    my_skills = user_skills.get(u.id, set())
                    if _DEBUG_SEASON_PLANNING:
                        logger.debug(
                            "SeasonPlanning: user=%s skills=%s", u.id, sorted(my_skills)
                        )
                    for skill in my_skills:
                        if skill not in supply:
                            supply[skill] = {}
                        if w not in supply[skill]:
                            supply[skill][w] = {"m": 0, "d": 0, "n": 0, "f": 0}

                        # We only track total days for now in the constraint?
                        # Step 1115 constraint uses: sum(supply.get(skill, {}).get(w, {}).values())
                        # So we must populate the dict values.
                        s = supply[skill][w]
                        s["m"] += aw.morning_days or 0
                        s["d"] += aw.daytime_days or 0
                        s["n"] += aw.nighttime_days or 0
                        s["f"] += aw.flex_days or 0  # Wait, line 181 summed them all?
                        # Actually original logic (Step 1020) summed them.
                        # Let's keep consistent structure.

                    if is_intern:
                        if w not in supply_intern:
                            supply_intern[w] = 0
                        supply_intern[w] += total_days

                    if is_supervisor:
                        if w not in supply_supervisor:
                            supply_supervisor[w] = 0
                        supply_supervisor[w] += total_days

        if _DEBUG_SEASON_PLANNING and _DEBUG_SEASON_PLANNING_VISIT_ID is not None:
            logger.debug(
                "SeasonPlanning: debug_visit_id=%s", _DEBUG_SEASON_PLANNING_VISIT_ID
            )

        # ... (Solver Model Setup) ...
        # [EXISTING MODEL SETUP]

        model = cp_model.CpModel()

        visit_week_vars = {}  # v.id -> IntVar
        visit_active_vars = {}  # v.id -> BoolVar

        debug_visit_candidate_weeks: dict[int, list[int]] = {}

        # To optimize the "Cumulative Capacity" constraint, we need to group visits by allowed weeks.
        # But visits have individual windows.
        # We will collect: allowed_visits_per_week[week][skill] -> list[ (v_id, overlap_days) ]
        visits_per_week_candidate = {}  # Week -> Skill -> list of (v, overlap)

        for v in visits:
            v_skill = SeasonPlanningService._get_required_user_flag(v)

            debug_this_visit = bool(
                _DEBUG_SEASON_PLANNING
                and _DEBUG_SEASON_PLANNING_VISIT_ID is not None
                and getattr(v, "id", None) == _DEBUG_SEASON_PLANNING_VISIT_ID
            )

            # Domain: Week numbers
            # Intersection of visit.from..to and horizon
            v_start = v.from_date or start_date
            v_end = v.to_date or date.max

            # Clamp dates to current year for week calc
            eff_start = max(v_start, date(year, 1, 1))
            eff_end = min(v_end, date(year, 12, 31))

            start_iso = eff_start.isocalendar()
            start_w = start_iso.week if start_iso.year == year else 1

            end_iso = eff_end.isocalendar()
            if end_iso.year > year:
                end_w = 53
            elif end_iso.year < year:
                end_w = 1
            else:
                end_w = end_iso.week

            # Handling year boundary for isocalendar (Dec 29 can be W1)
            # User said "Current Year Only". So strict integer range.
            # If dates spill over, we clamp.

            is_custom = bool(
                getattr(v, "custom_function_name", None)
                or getattr(v, "custom_species_name", None)
            )
            if is_custom:
                continue

            if debug_this_visit:
                supply_keys = sorted(supply.keys())
                is_urgent = False
                if getattr(v, "to_date", None) is not None:
                    try:
                        is_urgent = 0 <= (v.to_date - start_date).days <= 14
                    except Exception:
                        is_urgent = False
                logger.debug(
                    "SeasonPlanning(debug): visit=%s skill=%s part_of_day=%s req_res=%s from=%s to=%s urgent=%s supply_has_skill=%s supply_keys_sample=%s",
                    v.id,
                    v_skill,
                    getattr(v, "part_of_day", None),
                    getattr(v, "required_researchers", None),
                    getattr(v, "from_date", None),
                    getattr(v, "to_date", None),
                    is_urgent,
                    v_skill in supply,
                    supply_keys[:25],
                )

            # Create Vars
            suffix = f"_{v.id}"
            is_active = model.NewBoolVar(f"active{suffix}")
            visit_active_vars[v.id] = is_active

            # Domain
            valid_weeks = []

            # Use year-independent search of weeks for the year horizon
            # end_w can be 1 if it falls in next iso year, so we normalize
            eff_end_w = end_w
            if eff_end_w < start_w and eff_end_w < 5:
                eff_end_w = 53  # Handle W52/53 -> W1 wrap

            search_range = range(max(start_w, current_week), min(eff_end_w + 1, 54))

            domain_list = [0]  # 0 = Unassigned/Not Planned

            for w in search_range:
                if w > 53:
                    continue

                # Calculate Overlap for this week
                # Week W Monday
                try:
                    w_mon = date.fromisocalendar(year, w, 1)
                    w_fri = w_mon + timedelta(days=4)
                except ValueError:
                    # Some years don't have Week 53
                    continue

                # Intersection [eff_start, eff_end] vs [w_mon, w_fri]
                # Note: We consider Monday-Friday as planning days usually.
                overlap_start = max(eff_start, w_mon)
                overlap_end = min(eff_end, w_fri)

                days = (overlap_end - overlap_start).days + 1

                if days >= 1:  # Fits at least 1 day
                    if debug_this_visit:
                        sup_total = sum(supply.get(v_skill, {}).get(w, {}).values())
                        part_of_day = (getattr(v, "part_of_day", None) or "").strip()
                        part_key = {"Ochtend": "m", "Dag": "d", "Avond": "n"}.get(
                            part_of_day
                        )
                        sup_daypart = None
                        if part_key is not None:
                            sup_daypart = supply.get(v_skill, {}).get(w, {}).get(
                                part_key, 0
                            ) + supply.get(v_skill, {}).get(w, {}).get("f", 0)
                        req_res = getattr(v, "required_researchers", None) or 1
                        try:
                            req_res_int = int(req_res)
                        except (TypeError, ValueError):
                            req_res_int = 1
                        window_weight = math.ceil(5 / days)
                        logger.debug(
                            "SeasonPlanning(debug): visit=%s week=%s overlap_days=%s window_weight=%s demand=%s supply_total=%s supply_daypart=%s",
                            v.id,
                            w,
                            days,
                            window_weight,
                            req_res_int * window_weight,
                            sup_total,
                            sup_daypart,
                        )
                    if _DEBUG_SEASON_PLANNING:
                        logger.debug(
                            "SeasonPlanning: visit=%s valid_week=%s overlap_days=%s",
                            v.id,
                            w,
                            days,
                        )
                    valid_weeks.append(w)
                    domain_list.append(w)

                    if debug_this_visit:
                        debug_visit_candidate_weeks[v.id] = (
                            debug_visit_candidate_weeks.get(v.id, []) + [w]
                        )

                    # Store candidate for Constraint Generation
                    if w not in visits_per_week_candidate:
                        visits_per_week_candidate[w] = {}
                    if v_skill not in visits_per_week_candidate[w]:
                        visits_per_week_candidate[w][v_skill] = []

                    visits_per_week_candidate[w][v_skill].append((v, days, is_active))

            if len(domain_list) <= 1:  # Only [0]
                model.Add(is_active == 0)
                # Assign dummy 0
                visit_week_vars[v.id] = model.NewConstant(0)
                continue

            vw = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(domain_list), f"week{suffix}"
            )
            visit_week_vars[v.id] = vw

            # Link Active: Active <-> vw != 0
            model.Add(vw != 0).OnlyEnforceIf(is_active)
            model.Add(vw == 0).OnlyEnforceIf(is_active.Not())

            # HARD CONSTRAINTS (Anchors)
            # 1. Already Planned
            if v.planned_week:
                # If planned_week in domain?
                model.Add(vw == v.planned_week).OnlyEnforceIf(is_active)
                # Should we force active?
                # Yes, if it's planned, it IS active.
                model.Add(is_active == 1)

            # 2. Manual Lock
            elif v.provisional_locked and v.provisional_week:
                model.Add(vw == v.provisional_week).OnlyEnforceIf(is_active)
                model.Add(is_active == 1)

        # 3b. Sequence & Gap Constraints
        # Enforce start-date ordering and min gaps for visits sharing protocols.

        def _gap_weeks_from_protocol(proto: Protocol) -> int:
            """Convert protocol min-period to whole weeks (ceil) for gap constraint.

            Args:
                proto: Protocol model instance.

            Returns:
                Gap in whole weeks (ceil) or 0 if none configured.
            """

            val = proto.min_period_between_visits_value
            if val is None:
                return 0
            if not isinstance(val, (int, float)):
                return 0
            unit = (proto.min_period_between_visits_unit or "").lower()
            if "week" in unit:
                min_gap_days = val * 7
            elif "maand" in unit or "month" in unit:
                min_gap_days = val * 30
            else:
                min_gap_days = val
            return math.ceil(min_gap_days / 7) if min_gap_days > 0 else 0

        def _visit_start(v: Visit) -> date:
            """Return the visit start date used for ordering constraints.

            Args:
                v: Visit model instance.

            Returns:
                Best-available visit start date.
            """

            if getattr(v, "from_date", None):
                return v.from_date
            pvw_dates = [
                pvw.window_from
                for pvw in (v.protocol_visit_windows or [])
                if getattr(pvw, "window_from", None) is not None
            ]
            return min(pvw_dates) if pvw_dates else start_date

        def _protocol_visit_index(v: Visit, protocol_id: int) -> int | None:
            """Return the visit index for a specific protocol PVW.

            Args:
                v: Visit model instance.
                protocol_id: Protocol id to scope the visit index.

            Returns:
                Protocol visit index if available, otherwise None.
            """

            for pvw in v.protocol_visit_windows or []:
                if getattr(pvw, "protocol_id", None) != protocol_id:
                    continue
                visit_index = getattr(pvw, "visit_index", None)
                if isinstance(visit_index, int):
                    return visit_index
            return None

        def _protocol_visit_deadline(v: Visit, protocol_id: int) -> date | None:
            """Return the deadline date for a visit scoped to a protocol.

            Args:
                v: Visit model instance.
                protocol_id: Protocol id to scope the deadline.

            Returns:
                Deadline date if available.
            """

            for pvw in v.protocol_visit_windows or []:
                if getattr(pvw, "protocol_id", None) != protocol_id:
                    continue
                deadline = getattr(pvw, "window_to", None)
                if deadline:
                    return deadline
            return v.to_date

        def _deadline_week(deadline: date | None) -> int | None:
            """Convert a deadline date to an ISO week within the current year.

            Args:
                deadline: Deadline date to convert.

            Returns:
                ISO week number if deadline is available.
            """

            if deadline is None:
                return None
            iso = deadline.isocalendar()
            if iso.year > year:
                return 53
            if iso.year < year:
                return 1
            return iso.week

        def _protocol_window_weeks(v: Visit, protocol_id: int) -> int | None:
            """Return the protocol window length in weeks, if known.

            Args:
                v: Visit model instance.
                protocol_id: Protocol id to scope the window length.

            Returns:
                Window length in weeks (ceil) or None if unknown.
            """

            for pvw in v.protocol_visit_windows or []:
                if getattr(pvw, "protocol_id", None) != protocol_id:
                    continue
                start = getattr(pvw, "window_from", None)
                end = getattr(pvw, "window_to", None)
                if start and end:
                    return math.ceil(((end - start).days + 1) / 7)
            if v.from_date and v.to_date:
                return math.ceil(((v.to_date - v.from_date).days + 1) / 7)
            return None

        visit_protocols: dict[int, dict[int, Protocol]] = {}
        cluster_visits: dict[int, list[Visit]] = {}
        successor_risk_terms: list[cp_model.IntVar] = []

        for v in visits:
            if not v.protocol_visit_windows:
                continue
            proto_map: dict[int, Protocol] = {}
            for pvw in v.protocol_visit_windows:
                proto = getattr(pvw, "protocol", None)
                if proto and getattr(pvw, "protocol_id", None) is not None:
                    proto_map[pvw.protocol_id] = proto
            if not proto_map:
                continue
            visit_protocols[v.id] = proto_map
            if v.cluster_id is not None:
                cluster_visits.setdefault(v.cluster_id, []).append(v)

        for cluster_id, items in cluster_visits.items():
            if len(items) < 2:
                continue
            items.sort(key=_visit_start)
            for idx in range(len(items) - 1):
                v1 = items[idx]
                for jdx in range(idx + 1, len(items)):
                    v2 = items[jdx]
                    if v1.id not in visit_week_vars or v2.id not in visit_week_vars:
                        continue
                    protocols_1 = visit_protocols.get(v1.id, {})
                    protocols_2 = visit_protocols.get(v2.id, {})
                    shared_protocols = set(protocols_1).intersection(protocols_2)
                    if not shared_protocols:
                        continue
                    for pid in shared_protocols:
                        idx_1 = _protocol_visit_index(v1, pid)
                        idx_2 = _protocol_visit_index(v2, pid)
                        if idx_1 is None or idx_2 is None or idx_1 == idx_2:
                            continue
                        if idx_1 < idx_2:
                            earlier, later = v1, v2
                        else:
                            earlier, later = v2, v1

                        gap_weeks = _gap_weeks_from_protocol(protocols_1[pid])
                        w1 = visit_week_vars[earlier.id]
                        w2 = visit_week_vars[later.id]
                        a1 = visit_active_vars[earlier.id]
                        a2 = visit_active_vars[later.id]
                        model.Add(w2 > w1).OnlyEnforceIf([a1, a2])
                        if gap_weeks > 0:
                            model.Add(w2 >= w1 + gap_weeks).OnlyEnforceIf([a1, a2])

                        window_weeks = _protocol_window_weeks(later, pid)
                        if window_weeks is None or window_weeks > 2:
                            continue
                        later_deadline = _protocol_visit_deadline(later, pid)
                        deadline_week = _deadline_week(later_deadline)
                        if deadline_week is None or gap_weeks <= 0:
                            continue
                        latest_allowed = deadline_week - gap_weeks
                        if latest_allowed < 1:
                            continue
                        risk = model.NewIntVar(
                            0, 53, f"succ_risk_{earlier.id}_{later.id}_{pid}"
                        )
                        model.Add(risk >= w1 - latest_allowed).OnlyEnforceIf([a1, a2])
                        model.Add(risk == 0).OnlyEnforceIf(a1.Not())
                        model.Add(risk == 0).OnlyEnforceIf(a2.Not())
                        successor_risk_terms.append(risk)

        # 3b. Sequence & Gap Constraints
        # ... (Existing Sequence Logic - Not Touched)

        # [REDACTED PREVIOUS SEQUENCE LOGIC TO SAVE SPACE IF NOT CHANGING? NO, Context]

        # 3c. Sleutel (Hard) & Coupling (Soft) Constraints
        # Junior: Junior OR Flex
        # Supervisor: Senior OR (Intern AND Not Junior)
        junior_indices = []
        supervisor_indices = []

        for j, u in enumerate(users):
            contract = SeasonPlanningService._get_contract_value(u)
            exp = (getattr(u, "experience_bat", "") or "").lower()

            is_junior = exp == "junior" or contract == "flex"
            is_supervisor = exp == "senior" or (
                contract == "intern" and exp != "junior"
            )

            if is_junior:
                junior_indices.append(j)
            if is_supervisor:
                supervisor_indices.append(j)

        # Pre-calculate Project grouping for Diversity
        # project_id -> list of v_indices
        project_visits_indices = {}

        # We need visit->cluster->project.
        # visits list is passed.
        # But we need solver VARS.

        for i, v in enumerate(visits):
            if v.id not in visit_week_vars:
                continue

            vw = visit_week_vars[v.id]

            # Diversity Tracking
            # v.cluster is loaded? Yes in _load_all_active_visits.
            # v.cluster.project_id
            pid = getattr(getattr(v, "cluster", None), "project_id", None)
            if pid:
                if pid not in project_visits_indices:
                    project_visits_indices[pid] = []
                project_visits_indices[pid].append(i)

        # 4. Cumulative Daily Capacity Constraints (EXTENDED)
        # For each Week W, per Skill S
        overflow_penalty_terms = []
        quadratic_load_terms = []

        intern_shortfall_terms = []
        supervisor_shortfall_terms = []
        diversity_penalty_terms = []

        # Map: Week -> Skill -> List of (v, overlap, is_active)
        # We constructed 'visits_per_week_candidate' earlier.

        # Iterate all weeks that have ANY activity
        all_weeks = sorted(
            list(set(visits_per_week_candidate.keys()) | set(horizon_weeks))
        )
        # Ensure range
        horizon_weeks = range(min(all_weeks), max(all_weeks) + 1) if all_weeks else []

        overflow_by_week_skill: dict[tuple[int, str], cp_model.IntVar] = {}
        overflow_by_week_skill_daypart: dict[tuple[int, str, str], cp_model.IntVar] = {}
        overflow_global_by_week: dict[int, cp_model.IntVar] = {}

        slack_by_week_skill: dict[tuple[int, str], cp_model.IntVar] = {}
        slack_by_week_skill_daypart: dict[tuple[int, str, str], cp_model.IntVar] = {}
        slack_global_by_week: dict[int, cp_model.IntVar] = {}

        for w in horizon_weeks:
            # We need to collect demands for skills AND special constraints

            # 4a. Skill Demand
            skill_map = visits_per_week_candidate.get(w, {})

            week_assignments_cost = []  # For load balancing
            week_intern_demand = []
            week_supervisor_demand = []
            week_proj_counts = {}  # pid -> list of bools
            week_total_demand_terms = []
            week_daypart_demand_terms = {"m": [], "d": [], "n": []}

            # Iterate Skills
            for skill, candidates in skill_map.items():
                assigned_bools = []

                # Daypart demand buckets (only for visits with a known part_of_day)
                daypart_demand_terms = {"m": [], "d": [], "n": []}

                for v, overlap, is_active in candidates:
                    # Capture the boolean: vw == w
                    # We can create a new boolean since 'vw' is global
                    vw = visit_week_vars[v.id]
                    b = model.NewBoolVar(f"assigned_{v.id}_{w}_{skill}")
                    model.Add(vw == w).OnlyEnforceIf(b)
                    model.Add(vw != w).OnlyEnforceIf(b.Not())

                    # Ensure consistency with is_active
                    model.AddImplication(b, is_active)

                    assigned_bools.append(b)

                    # Track for BALANCING
                    cost = v.required_researchers or 1
                    week_assignments_cost.append(b * cost)

                    # --- SLEUTEL (Intern) ---
                    if getattr(v, "sleutel", False):
                        window_weight = math.ceil(5 / overlap)
                        week_intern_demand.append(b * window_weight)

                    # --- COUPLING (Supervisor) ---
                    if (v.required_researchers or 1) > 1:
                        fam_name = (
                            str(
                                getattr(
                                    getattr(v, "species", [None])[0], "family", None
                                )
                                and getattr(
                                    getattr(v.species[0], "family", None), "name", ""
                                )
                                or ""
                            )
                            .strip()
                            .lower()
                        )
                        if fam_name == "vleermuis":
                            # Soft Coupling: Demand Supervisor for multi-person Vleermuis
                            window_weight = math.ceil(5 / overlap)
                            week_supervisor_demand.append(b * window_weight)

                    # --- DIVERSITY ---
                    pid = getattr(getattr(v, "cluster", None), "project_id", None)
                    if pid:
                        if pid not in week_proj_counts:
                            week_proj_counts[pid] = []
                        week_proj_counts[pid].append(b)

                # Skill Volume Constraint
                sup_total = sum(supply.get(skill, {}).get(w, {}).values())

                if _DEBUG_SEASON_PLANNING:
                    logger.debug(
                        "SeasonPlanning: week=%s skill=%s supply=%s candidates=%s",
                        w,
                        skill,
                        sup_total,
                        len(candidates),
                    )

                if assigned_bools:
                    overflow = model.NewIntVar(0, 10000, f"overflow_{w}_{skill}")
                    overflow_penalty_terms.append(overflow)
                    overflow_by_week_skill[(w, skill)] = overflow

                    # Demand = Sum(assigned_bool_i * researchers_i * days_i)
                    demand_terms = []
                    for i, b in enumerate(assigned_bools):
                        v_cand = candidates[i][0]
                        overlap_days = candidates[i][1]
                        # Ensure researchers is an int
                        req_res = v_cand.required_researchers or 1
                        if hasattr(req_res, "__int__") or isinstance(
                            req_res, (int, float)
                        ):
                            req_res = int(req_res)
                        else:
                            req_res = 1  # Fallback for Mocks

                        window_weight = math.ceil(5 / overlap_days)
                        term = b * (req_res * window_weight)
                        demand_terms.append(term)
                        week_total_demand_terms.append(term)

                        # Daypart-aware accounting (approximate):
                        # If a visit is tagged as a specific daypart, it can only
                        # consume that daypart capacity plus flex.
                        part_of_day = (
                            getattr(v_cand, "part_of_day", None) or ""
                        ).strip()
                        part_key = {"Ochtend": "m", "Dag": "d", "Avond": "n"}.get(
                            part_of_day
                        )
                        if part_key is not None:
                            daypart_demand_terms[part_key].append(
                                b * (req_res * window_weight)
                            )
                            week_daypart_demand_terms[part_key].append(
                                b * (req_res * window_weight)
                            )

                    model.Add(
                        cp_model.LinearExpr.Sum(demand_terms) <= sup_total + overflow
                    )

                    if (
                        _DEBUG_SEASON_PLANNING
                        and _DEBUG_SEASON_PLANNING_VISIT_ID is not None
                    ):
                        slack = model.NewIntVar(0, 10000, f"slack_{w}_{skill}")
                        model.Add(
                            slack
                            == sup_total
                            + overflow
                            - cp_model.LinearExpr.Sum(demand_terms)
                        )
                        slack_by_week_skill[(w, skill)] = slack

                    # Additional hardening: enforce daypart capacity separately.
                    # This prevents "morning" capacity being used for an evening-only visit.
                    for part_key, d_terms in daypart_demand_terms.items():
                        if not d_terms:
                            continue
                        sup_daypart = supply.get(skill, {}).get(w, {}).get(
                            part_key, 0
                        ) + supply.get(skill, {}).get(w, {}).get("f", 0)
                        overflow_dp = model.NewIntVar(
                            0, 10000, f"overflow_{w}_{skill}_{part_key}"
                        )
                        overflow_penalty_terms.append(overflow_dp)
                        overflow_by_week_skill_daypart[(w, skill, part_key)] = (
                            overflow_dp
                        )
                        model.Add(
                            cp_model.LinearExpr.Sum(d_terms)
                            <= sup_daypart + overflow_dp
                        )

                        if (
                            _DEBUG_SEASON_PLANNING
                            and _DEBUG_SEASON_PLANNING_VISIT_ID is not None
                        ):
                            slack_dp = model.NewIntVar(
                                0, 10000, f"slack_{w}_{skill}_{part_key}"
                            )
                            model.Add(
                                slack_dp
                                == sup_daypart
                                + overflow_dp
                                - cp_model.LinearExpr.Sum(d_terms)
                            )
                            slack_by_week_skill_daypart[(w, skill, part_key)] = slack_dp

            # 4b. Load Balancing
            if week_assignments_cost:
                load_w = model.NewIntVar(0, 10000, f"load_{w}")
                model.Add(load_w == sum(week_assignments_cost))
                sq_load = model.NewIntVar(0, 100000000, f"sq_load_{w}")
                model.AddMultiplicationEquality(sq_load, [load_w, load_w])
                quadratic_load_terms.append(sq_load)

            # 4c. Intern Shortfall
            if week_intern_demand:
                total_intern = supply_intern.get(w, 0)
                sf_int = model.NewIntVar(0, 10000, f"short_intern_{w}")
                intern_shortfall_terms.append(sf_int)
                model.Add(sum(week_intern_demand) <= total_intern + sf_int)

            # 4d. Supervisor Shortfall
            if week_supervisor_demand:
                total_sup = supply_supervisor.get(w, 0)
                sf_sup = model.NewIntVar(0, 10000, f"short_sup_{w}")
                supervisor_shortfall_terms.append(sf_sup)
                model.Add(sum(week_supervisor_demand) <= total_sup + sf_sup)

            # 4e. Diversity (Penalty)
            for pid, bools in week_proj_counts.items():
                if len(bools) > 1:
                    # Count assigned
                    c = model.NewIntVar(0, len(bools), f"p_count_{w}_{pid}")
                    model.Add(c == sum(bools))

                    excess = model.NewIntVar(0, len(bools), f"p_excess_{w}_{pid}")
                    model.Add(excess >= c - 1)
                    diversity_penalty_terms.append(excess)

            fixed_custom_demand = custom_fixed_demand_by_week.get(w, 0)
            if week_total_demand_terms or fixed_custom_demand:
                global_supply_w = 0
                for u in users:
                    aw = avail_map.get((u.id, w))
                    if not aw:
                        continue
                    global_supply_w += (
                        (aw.morning_days or 0)
                        + (aw.daytime_days or 0)
                        + (aw.nighttime_days or 0)
                        + (aw.flex_days or 0)
                    )

                overflow_global = model.NewIntVar(0, 10000, f"overflow_global_{w}")
                overflow_penalty_terms.append(overflow_global)
                overflow_global_by_week[w] = overflow_global
                model.Add(
                    cp_model.LinearExpr.Sum(week_total_demand_terms)
                    + fixed_custom_demand
                    <= global_supply_w + overflow_global
                )

            for part_key in ("m", "d", "n"):
                fixed_custom_daypart = custom_fixed_demand_by_week_daypart.get(
                    (w, part_key), 0
                )
                if not week_daypart_demand_terms[part_key] and not fixed_custom_daypart:
                    continue

                global_part_supply = 0
                for u in users:
                    aw = avail_map.get((u.id, w))
                    if not aw:
                        continue
                    if part_key == "m":
                        global_part_supply += (aw.morning_days or 0) + (
                            aw.flex_days or 0
                        )
                    elif part_key == "d":
                        global_part_supply += (aw.daytime_days or 0) + (
                            aw.flex_days or 0
                        )
                    else:
                        global_part_supply += (aw.nighttime_days or 0) + (
                            aw.flex_days or 0
                        )

                overflow_global_part = model.NewIntVar(
                    0, 10000, f"overflow_global_{w}_{part_key}"
                )
                overflow_penalty_terms.append(overflow_global_part)
                model.Add(
                    cp_model.LinearExpr.Sum(week_daypart_demand_terms[part_key])
                    + fixed_custom_daypart
                    <= global_part_supply + overflow_global_part
                )

                if (
                    _DEBUG_SEASON_PLANNING
                    and _DEBUG_SEASON_PLANNING_VISIT_ID is not None
                ):
                    slack_global = model.NewIntVar(0, 100000, f"slack_global_{w}")
                    model.Add(
                        slack_global
                        == global_supply_w
                        + overflow_global
                        - (
                            cp_model.LinearExpr.Sum(week_total_demand_terms)
                            + fixed_custom_demand
                        )
                    )
                    slack_global_by_week[w] = slack_global

            # --- Sleutel Constraint (Hard) ---
            if getattr(v, "sleutel", False):
                # If active, MUST have intern
                pass
                # WAIT. Season Planner does NOT assign Users to Visits!
                # It assigns Visits to Weeks.
                # "Who goes" is decided by Weekly Solver.
                #
                # CRITICAL REALIZATION:
                # Season Planner only decides provisional_week.
                # It calculates feasibility based on AGGREGATE capacity.
                # It does NOT assign specific x[v, u] variables.
                #
                # Therefore, I CANNOT enforce "This visit has an intern" because I don't know who goes!
                #
                # I messed up the implementation plan assumption.
                # The user said: "Since now we actually use the seasonal planner to determine which visits we should do... we should do the tight validation."
                # But `solve_season` as implemented is creating `visit_week_vars`.
                # It sums capacity `supply` vs `demand`.
                #
                # To enforce Sleutel/Coupling, I must ensure valid capacity exists *of that type*.
                #
                # Sleutel: "Need 1 Intern".
                # Means: In Week W, we need `Intern Days >= Sum(Sleutel Visits)`.
                #
                # Coupling: "Need 1 Senior per Multi-Junior Visit".
                # Means: `Senior/Supervisor Days >= Junior-Heavy Visits`.
                #
                # This changes the Implementation. I cannot use `x[v, u]` constraints because they don't exist.
                # I must add NEW CAPACITY TYPES.
                #
                # 1. Supply["Intern"]
                # 2. Supply["Supervisor"]
                #
                # And generated "Demand":
                # For each Sleutel Visit -> Demand["Intern"] += 1.
                # For each Multi-person Visit -> Demand["Supervisor"] += 1 (Approximation? Or just "Supervisor Capacity"?)
                #
                # Project Diversity: checking if we pile too many visits of same project into one week?
                # Yes, that I can do. `Sum(v for v in Project P if v.week == W) <= threshold`?
                # Or just soft penalty on square of counts.
                #
                # I need to Pivot.
                # I will modify the code to:
                # 1. Add "Intern" and "Supervisor" as pseudo-skills in Supply.
                # 2. Add Demand for them based on visit attributes.
                # 3. Add Project Diversity Penalty based on visit week counts.
                #
                pass

        # ... (Pivot to new logic below)

        # 5. Objective
        # Split into components for clarity/debugging

        # Active Rewards
        active_vars = []
        urgent_active_vars = []
        priority_active_vars = []
        for v in visits:
            if v.id in visit_active_vars:
                active_vars.append(visit_active_vars[v.id])
                if getattr(v, "priority", False):
                    priority_active_vars.append(visit_active_vars[v.id])
                if v.to_date is not None and 0 <= (v.to_date - start_date).days <= 14:
                    urgent_active_vars.append(visit_active_vars[v.id])

        # Base Reward: 100,000 per active visit
        # Using LinearExpr.Sum to ensuring efficient summing
        reward_term = cp_model.LinearExpr.Sum(active_vars) * 100000

        urgent_reward_term = cp_model.LinearExpr.Sum(urgent_active_vars) * 150000

        priority_reward_term = cp_model.LinearExpr.Sum(priority_active_vars) * 50000

        # Slack Penalties (Early Preference)
        slack_terms = []
        for v in visits:
            if v.id in visit_week_vars and v.to_date:
                dw = v.to_date.isocalendar().week
                vw = visit_week_vars[v.id]
                if dw >= current_week:
                    slack_terms.append(vw)

        slack_penalty = cp_model.LinearExpr.Sum(slack_terms) * -10

        # Constraint Penalties
        # 200k for Overflow matches 2 Active visits.
        # So 1 overflow cancels 2 visits?
        # If Demand=1, Supply=0 -> Overflow=1.
        # Active=1 (Reward 100k). Overflow=1 (Penalty -200k). Result -100k. Inactive preferred. Correct.
        #
        p_overflow = cp_model.LinearExpr.Sum(overflow_penalty_terms) * -200000
        p_intern = cp_model.LinearExpr.Sum(intern_shortfall_terms) * -200000
        p_supervisor = cp_model.LinearExpr.Sum(supervisor_shortfall_terms) * -100
        p_diversity = cp_model.LinearExpr.Sum(diversity_penalty_terms) * -10
        p_successor_risk = cp_model.LinearExpr.Sum(successor_risk_terms) * -500

        scaled_load_terms = []
        for idx, term in enumerate(quadratic_load_terms):
            scaled = model.NewIntVar(0, 100000000, f"sq_load_scaled_{idx}")
            model.AddDivisionEquality(scaled, term, 10)
            scaled_load_terms.append(scaled)
        p_load = cp_model.LinearExpr.Sum(scaled_load_terms) * -1

        total_obj = (
            reward_term
            + urgent_reward_term
            + priority_reward_term
            + slack_penalty
            + p_overflow
            + p_intern
            + p_supervisor
            + p_diversity
            + p_successor_risk
            + p_load
        )
        model.Maximize(total_obj)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0  # Reasonable limit
        status = solver.Solve(model)

        if _DEBUG_SEASON_PLANNING:
            logger.debug("SeasonPlanning: solver_status=%s", solver.StatusName(status))
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                logger.debug("SeasonPlanning: objective=%s", solver.ObjectiveValue())

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if _DEBUG_SEASON_PLANNING and _DEBUG_SEASON_PLANNING_VISIT_ID is not None:
                for v in visits:
                    if getattr(v, "id", None) != _DEBUG_SEASON_PLANNING_VISIT_ID:
                        continue
                    if v.id not in visit_week_vars:
                        logger.debug(
                            "SeasonPlanning(debug): visit=%s no_var_created",
                            v.id,
                        )
                        break

                    active = solver.Value(visit_active_vars[v.id])
                    chosen_week = solver.Value(visit_week_vars[v.id])
                    v_skill = SeasonPlanningService._get_required_user_flag(v)
                    part_of_day = (getattr(v, "part_of_day", None) or "").strip()
                    part_key = {"Ochtend": "m", "Dag": "d", "Avond": "n"}.get(
                        part_of_day
                    )
                    global_supply_w = 0
                    if chosen_week:
                        for u in users:
                            aw = avail_map.get((u.id, chosen_week))
                            if not aw:
                                continue
                            global_supply_w += (
                                (aw.morning_days or 0)
                                + (aw.daytime_days or 0)
                                + (aw.nighttime_days or 0)
                                + (aw.flex_days or 0)
                            )

                    overflow_global_val = None
                    overflow_skill_val = None
                    overflow_daypart_val = None
                    if chosen_week:
                        ov_g = overflow_global_by_week.get(chosen_week)
                        if ov_g is not None:
                            overflow_global_val = solver.Value(ov_g)
                        ov_s = overflow_by_week_skill.get((chosen_week, v_skill))
                        if ov_s is not None:
                            overflow_skill_val = solver.Value(ov_s)
                        if part_key is not None:
                            ov_dp = overflow_by_week_skill_daypart.get(
                                (chosen_week, v_skill, part_key)
                            )
                            if ov_dp is not None:
                                overflow_daypart_val = solver.Value(ov_dp)

                    logger.debug(
                        "SeasonPlanning(debug): visit=%s solver_active=%s solver_week=%s global_supply=%s overflow_global=%s overflow_skill=%s overflow_daypart=%s",
                        v.id,
                        active,
                        chosen_week,
                        global_supply_w,
                        overflow_global_val,
                        overflow_skill_val,
                        overflow_daypart_val,
                    )

                    candidate_weeks = debug_visit_candidate_weeks.get(v.id, [])
                    if candidate_weeks:
                        logger.debug(
                            "SeasonPlanning(debug): visit=%s candidate_weeks=%s",
                            v.id,
                            candidate_weeks,
                        )
                    for cw in candidate_weeks:
                        ov_g = overflow_global_by_week.get(cw)
                        sl_g = slack_global_by_week.get(cw)
                        ov_s = overflow_by_week_skill.get((cw, v_skill))
                        sl_s = slack_by_week_skill.get((cw, v_skill))
                        ov_dp = None
                        sl_dp = None
                        if part_key is not None:
                            ov_dp = overflow_by_week_skill_daypart.get(
                                (cw, v_skill, part_key)
                            )
                            sl_dp = slack_by_week_skill_daypart.get(
                                (cw, v_skill, part_key)
                            )
                        logger.debug(
                            "SeasonPlanning(debug): visit=%s week=%s slack_global=%s overflow_global=%s slack_skill=%s overflow_skill=%s slack_daypart=%s overflow_daypart=%s",
                            v.id,
                            cw,
                            solver.Value(sl_g) if sl_g is not None else None,
                            solver.Value(ov_g) if ov_g is not None else None,
                            solver.Value(sl_s) if sl_s is not None else None,
                            solver.Value(ov_s) if ov_s is not None else None,
                            solver.Value(sl_dp) if sl_dp is not None else None,
                            solver.Value(ov_dp) if ov_dp is not None else None,
                        )
                    break

            # 6. Save Results
            for v in visits:
                if v.id in visit_week_vars:
                    active = solver.Value(visit_active_vars[v.id])

                    if active:
                        week_val = solver.Value(visit_week_vars[v.id])
                        if not v.provisional_locked or v.provisional_week is None:
                            v.provisional_week = week_val
                    else:
                        if not v.provisional_locked or v.provisional_week is None:
                            v.provisional_week = None

    @staticmethod
    async def get_capacity_grid(
        db: AsyncSession,
        start_date: date,
        *,
        include_quotes: bool = False,
    ) -> CapacitySimulationResponse:
        """
        Returns the Season Plan as a capacity grid.
        Replaces the old simulation service.
        Reads `provisional_week` from visits and aggregates them against supply.

        Args:
            db: Async SQLAlchemy session.
            start_date: Simulation start date.
            include_quotes: When True, include quote projects in the demand grid.
        """
        # Load visits and users
        visits = await SeasonPlanningService._load_all_active_visits(
            db, start_date, include_quotes=include_quotes
        )
        users = await SeasonPlanningService._load_all_users(db)

        year = start_date.year
        avail_map = await SeasonPlanningService._load_availability_map(db, year)
        return SeasonPlanningService._build_capacity_grid(
            start_date, visits, users, avail_map
        )

    @staticmethod
    async def simulate_capacity_grid(
        db: AsyncSession,
        start_date: date,
        *,
        include_quotes: bool = False,
    ) -> CapacitySimulationResponse:
        """Simulate the seasonal planner without persisting provisional weeks.

        Args:
            db: Async SQLAlchemy session.
            start_date: Simulation start date.
            include_quotes: When True, include quote projects in the solver input.

        Returns:
            Simulated capacity grid.
        """
        visits = await SeasonPlanningService._load_all_active_visits(
            db, start_date, include_quotes=include_quotes
        )
        users = await SeasonPlanningService._load_all_users(db)
        avail_map = await SeasonPlanningService._load_availability_map(
            db, start_date.year
        )

        SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

        result = SeasonPlanningService._build_capacity_grid(
            start_date, visits, users, avail_map
        )
        await db.rollback()
        return result

    @staticmethod
    def _build_capacity_grid(
        start_date: date,
        visits: list[Visit],
        users: list[User],
        avail_map: dict[tuple[int, int], AvailabilityWeek],
    ) -> CapacitySimulationResponse:
        """Build a capacity grid based on visits and availability.

        Args:
            start_date: Simulation start date.
            visits: Visits to include in the grid.
            users: Researchers used to compute capacity.
            avail_map: Mapping of (user_id, week) to availability.

        Returns:
            Capacity grid response.
        """
        year = start_date.year
        current_week = start_date.isocalendar().week
        demand_by_week: dict[int, int] = {}
        demand_by_skill: dict[str, dict[int, int]] = {}
        demand_by_skill_part: dict[str, dict[str, dict[int, int]]] = {}
        demand_weeks: set[int] = set()

        for v in visits:
            is_custom = bool(v.custom_function_name or v.custom_species_name)
            if is_custom:
                continue

            skill = SeasonPlanningService._get_required_user_flag(v)
            part = (v.part_of_day or "Onbekend").strip()
            part_key = part if part in {"Ochtend", "Dag", "Avond"} else "Onbekend"

            required = getattr(v, "required_researchers", None) or 1
            try:
                required_int = int(required)
            except (TypeError, ValueError):
                required_int = 1

            v_start = v.from_date or start_date
            v_end = v.to_date or date.max

            eff_start = max(v_start, date(year, 1, 1))
            eff_end = min(v_end, date(year, 12, 31))

            start_iso = eff_start.isocalendar()
            start_w = start_iso.week if start_iso.year == year else 1

            end_iso = eff_end.isocalendar()
            if end_iso.year > year:
                end_w = 53
            elif end_iso.year < year:
                end_w = 1
            else:
                end_w = end_iso.week

            eff_end_w = end_w
            if eff_end_w < start_w and eff_end_w < 5:
                eff_end_w = 53

            search_range = range(max(start_w, current_week), min(eff_end_w + 1, 54))
            for w in search_range:
                if w > 53:
                    continue
                try:
                    w_mon = date.fromisocalendar(year, w, 1)
                    w_fri = w_mon + timedelta(days=4)
                except ValueError:
                    continue

                overlap_start = max(eff_start, w_mon)
                overlap_end = min(eff_end, w_fri)
                overlap_days = (overlap_end - overlap_start).days + 1

                if overlap_days < 1:
                    continue

                demand_weeks.add(w)
                window_weight = math.ceil(5 / overlap_days)
                demand = required_int * window_weight

                demand_by_week[w] = demand_by_week.get(w, 0) + demand
                demand_by_skill.setdefault(skill, {})
                demand_by_skill[skill][w] = demand_by_skill[skill].get(w, 0) + demand

                demand_by_skill_part.setdefault(skill, {})
                demand_by_skill_part[skill].setdefault(part_key, {})
                demand_by_skill_part[skill][part_key][w] = (
                    demand_by_skill_part[skill][part_key].get(w, 0) + demand
                )

        # Generate Supply Map (Skill -> Week -> Capacity)
        user_skills = {
            u.id: SeasonPlanningService._get_user_skill_keys(u) for u in users
        }
        supply_map = {}  # Skill -> Week -> Count
        supply_map_part = {}  # Skill -> Part -> Week -> Count

        # Map active Horizon
        weeks = sorted(
            list(
                set(
                    (v.provisional_week or v.planned_week)
                    for v in visits
                    if (v.provisional_week or v.planned_week)
                )
                | {start_date.isocalendar().week}
                | demand_weeks
            )
        )
        # Ensure range
        horizon_weeks = range(min(weeks), max(weeks) + 1) if weeks else []

        for w in horizon_weeks:
            for u in users:
                aw = avail_map.get((u.id, w))
                if not aw:
                    continue

                m = aw.morning_days or 0
                d = aw.daytime_days or 0
                n = aw.nighttime_days or 0
                f = aw.flex_days or 0
                total_days = m + d + n + f
                if total_days <= 0:
                    continue

                for skill in user_skills.get(u.id, set()):
                    if skill not in supply_map:
                        supply_map[skill] = {}
                    supply_map[skill][w] = supply_map[skill].get(w, 0) + total_days

                    if skill not in supply_map_part:
                        supply_map_part[skill] = {}
                    for part, part_days in (
                        ("Ochtend", m + f),
                        ("Dag", d + f),
                        ("Avond", n + f),
                    ):
                        if part not in supply_map_part[skill]:
                            supply_map_part[skill][part] = {}
                        supply_map_part[skill][part][w] = (
                            supply_map_part[skill][part].get(w, 0) + part_days
                        )

        # Aggregate Demands
        # Family -> Part -> Week -> {planned, shortfall}
        # Actually Week View structure is Row -> Week -> {spare, planned}
        #
        week_view_rows = {}
        deadline_grid = {}  # Legacy deadline view

        # Helper structures
        planned_demand = {}  # (Skill, Week) -> count
        planned_by_skill_part: dict[str, dict[str, dict[str, int]]] = {}
        planned_total_by_week: dict[int, int] = {}

        for v in visits:
            is_custom = bool(v.custom_function_name or v.custom_species_name)
            if is_custom:
                skill = "Custom"
                is_planned = (v.provisional_week or v.planned_week) is not None
            else:
                skill = SeasonPlanningService._get_required_user_flag(v)
                is_planned = v.provisional_week is not None
            part = (v.part_of_day or "Onbekend").strip()

            # Deadline View Logic (Unchanged mostly)
            deadline = v.to_date.isoformat() if v.to_date else "No Deadline"
            if skill not in deadline_grid:
                deadline_grid[skill] = {}
            if part not in deadline_grid[skill]:
                deadline_grid[skill][part] = {}

            current = deadline_grid[skill][part].get(
                deadline, {"required": 0, "assigned": 0, "shortfall": 0}
            )

            cost = (
                len(v.researchers) if v.researchers else (v.required_researchers or 1)
            )

            current["required"] += cost

            if is_planned:
                current["assigned"] += cost
                deadline_grid[skill][part][deadline] = current

                # Week View Logic
                wk = v.provisional_week or v.planned_week
                if wk is not None:
                    planned_total_by_week[wk] = planned_total_by_week.get(wk, 0) + cost
                week_iso = f"{year}-W{wk:02d}"
                if skill not in planned_demand:
                    planned_demand[skill] = {}
                planned_demand[skill][week_iso] = (
                    planned_demand[skill].get(week_iso, 0) + cost
                )

                planned_by_skill_part.setdefault(skill, {})
                planned_by_skill_part[skill].setdefault(part, {})
                planned_by_skill_part[skill][part][week_iso] = (
                    planned_by_skill_part[skill][part].get(week_iso, 0) + cost
                )

                # Add to Week Row
                lbl = f"{skill} - {part}"
                if lbl not in week_view_rows:
                    week_view_rows[lbl] = {}
                curr_row = week_view_rows[lbl].get(
                    week_iso, {"spare": 0, "planned": 0, "shortage": 0}
                )
                curr_row["planned"] += cost
                week_view_rows[lbl][week_iso] = curr_row
            else:
                current["shortfall"] += cost
                deadline_grid[skill][part][deadline] = current

        # Calculate Spare Capacity for Week View
        # Spare = Supply - Demand
        # Note: Supply is per Skill.
        # Week View Rows are "Skill - Part".
        # We assign Spare to the rows? Or just Totalen?
        # Simulation service tried to split spare.
        for skill, parts in demand_by_skill_part.items():
            for part in parts:
                lbl = f"{skill} - {part}"
                week_view_rows.setdefault(lbl, {})
        # Let's aggregate Totalen first.

        for w in horizon_weeks:
            week_iso = f"{year}-W{w:02d}"

            total_supply_w = 0  # Unique person-days?
            # Summing skills double counts!
            # Total Supply is sum of all users' days.

            # Global Supply for Totalen
            global_days = 0
            for u in users:
                aw = avail_map.get((u.id, w))
                global_days += (
                    (
                        (aw.morning_days or 0)
                        + (aw.daytime_days or 0)
                        + (aw.nighttime_days or 0)
                        + (aw.flex_days or 0)
                    )
                    if aw
                    else 0
                )

            total_supply_w = global_days

            # Total Demand
            total_demand_w = demand_by_week.get(w, 0)

            # Totalen Row
            if "Totalen" not in week_view_rows:
                week_view_rows["Totalen"] = {}
            week_view_rows["Totalen"][week_iso] = {
                "spare": max(0, total_supply_w - planned_total_by_week.get(w, 0)),
                "planned": min(planned_total_by_week.get(w, 0), total_supply_w),
                "shortage": max(0, total_demand_w - total_supply_w),
            }

            # Per Skill Spare?
            # Spare(Skill) = Supply(Skill) - Demand(Skill)
            # We can backfill this into the rows.
            for row_key in week_view_rows:
                if row_key == "Totalen":
                    continue
                if " - " not in row_key:
                    continue
                skill, part = row_key.split(" - ", 1)
                if not skill:
                    continue

                if week_iso not in week_view_rows[row_key]:
                    week_view_rows[row_key][week_iso] = {
                        "spare": 0,
                        "planned": 0,
                        "shortage": 0,
                    }

                planned = week_view_rows[row_key][week_iso]["planned"]

                # For part-specific rows, align with the season solver:
                # Ochtend/Dag/Avond use (part + flex). Unknown parts fall back to total skill.
                if part in {"Ochtend", "Dag", "Avond"}:
                    part_supply = supply_map_part.get(skill, {}).get(part, {}).get(w, 0)
                    demand = demand_by_skill_part.get(skill, {}).get(part, {}).get(w, 0)
                else:
                    part_supply = supply_map.get(skill, {}).get(w, 0)
                    demand = demand_by_skill.get(skill, {}).get(w, 0)

                week_view_rows[row_key][week_iso]["spare"] = max(
                    0, part_supply - planned
                )
                week_view_rows[row_key][week_iso]["shortage"] = max(
                    0, demand - part_supply
                )

        return CapacitySimulationResponse(
            horizon_start=start_date,
            horizon_end=date(year, 12, 31),
            grid=deadline_grid,
            week_view={
                "weeks": [f"{year}-W{w:02d}" for w in horizon_weeks],
                "rows": week_view_rows,
            },
        )

    @staticmethod
    async def _load_all_active_visits(
        db: AsyncSession,
        start_date: date,
        *,
        include_quotes: bool = True,
    ) -> list[Visit]:
        """
        Load visits relevant for season planning.
        Includes:
        - Open visits (no result yet)
        - Quote visits (optional)
        - Even 'planned' visits (because we need them as anchors)
        Excludes:
        - Cancelled / Executed in past (unless we need them for gap logic?)

        Args:
            db: Async SQLAlchemy session.
            start_date: Start date for the planning horizon.
            include_quotes: When True, include quote projects.

        Returns:
            List of visits matching the criteria.
        """
        stmt = (
            select(Visit)
            .join(Cluster, Visit.cluster_id == Cluster.id)
            .join(Project, Cluster.project_id == Project.id)
            .where(
                or_(Visit.to_date >= start_date, Visit.to_date.is_(None)),
                # Exclude hard-deleted/soft-deleted handled by mixin usually, but check.
                # Project.status != 'cancelled' ? (Assume active)
            )
            .options(
                selectinload(Visit.functions),
                selectinload(Visit.species).selectinload(Species.family),
                selectinload(Visit.researchers),
                selectinload(Visit.cluster).selectinload(Cluster.project),
                selectinload(Visit.protocol_visit_windows).selectinload(
                    ProtocolVisitWindow.protocol
                ),
            )
        )
        if not include_quotes:
            stmt = stmt.where(or_(Project.quote.is_(False), Project.quote.is_(None)))
        return (await db.execute(stmt)).scalars().unique().all()

    @staticmethod
    async def _load_all_users(db: AsyncSession) -> list[User]:
        stmt = select(User).where(User.deleted_at.is_(None))
        return (await db.execute(stmt)).scalars().all()

    @staticmethod
    async def _load_availability_map(
        db: AsyncSession, year: int
    ) -> dict[tuple[int, int], AvailabilityWeek]:
        """Load availability rows and index them by (user_id, week).

        Args:
            db: Async SQLAlchemy session.
            year: ISO year for which the solver runs. The current
                AvailabilityWeek model is only keyed by ISO week number,
                so this value is currently not used for filtering.

        Returns:
            Mapping from (user_id, week) to AvailabilityWeek.
        """

        _ = year

        stmt = select(AvailabilityWeek).where(AvailabilityWeek.deleted_at.is_(None))
        rows = (await db.execute(stmt)).scalars().all()
        return {(r.user_id, r.week): r for r in rows}

    @staticmethod
    async def _load_all_availability(
        db: AsyncSession, start: date, end: date
    ) -> list[AvailabilityWeek]:
        # Load simplistic sum of availability?
        # Actually need breakdown for constraints.
        # But for 'Season' we assume weekly buckets.
        # ... fetch range ...
        return []

    @staticmethod
    def _week_id(d: date) -> int:
        return d.isocalendar().week  # Simplified, handle year crossing later

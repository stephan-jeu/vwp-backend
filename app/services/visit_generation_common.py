from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta, time
from typing import Any

from app.models.protocol import Protocol
from app.models.visit import Visit

_logger = logging.getLogger("uvicorn.error")

_PRECIPITATION_ORDER = [
    "motregen",
    "geen regen",
    "droog",
    "geen neerslag, geen mist boven watergangen",
]
_PRECIPITATION_PRIORITY = {name: idx for idx, name in enumerate(_PRECIPITATION_ORDER)}

# Minimum acceptable effective window length (days)
MIN_EFFECTIVE_WINDOW_DAYS = int(os.getenv("MIN_EFFECTIVE_WINDOW_DAYS", "10"))
_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}


# ---- Effective Timing --------------------------------------------------------

@dataclass
class EffectiveTiming:
    """Consolidated timing properties for a protocol after exception resolution."""
    protocol_id: int
    start_timing_reference: str | None
    start_time_absolute_from: time | None
    start_time_relative_minutes: int | None
    visit_duration_hours: float | None


def _get_effective_timing(p: Protocol, visit_index: int | None = None, part_of_day: str | None = None) -> EffectiveTiming:
    """Resolve effective timing for a protocol, applying exceptions (RD v1, MV)."""
    
    eff = EffectiveTiming(
        protocol_id=p.id,
        start_timing_reference=getattr(p, "start_timing_reference", None),
        start_time_absolute_from=getattr(p, "start_time_absolute_from", None),
        start_time_relative_minutes=getattr(p, "start_time_relative_minutes", None),
        visit_duration_hours=getattr(p, "visit_duration_hours", None)
    )

    fn = getattr(p, "function", None)
    sp = getattr(p, "species", None)
    fn_name = fn.name if fn else ""
    sp_abbr = sp.abbreviation if sp else ""
    sp_name = sp.name if sp else ""

    is_paarverblijf = (fn_name == "Paarverblijf")
    is_rd = (sp_abbr == "RD")
    is_mv = (sp_abbr == "MV" or sp_name == "MV")

    # EXCEPTION: MV Paarverblijf -> Override to Sunset for Evening
    if is_paarverblijf and is_mv and part_of_day == "Avond":
         eff.start_timing_reference = "SUNSET"
         eff.start_time_relative_minutes = 0

    # EXCEPTION: RD Paarverblijf Visit 1 -> Force Absolute 00:00
    if is_paarverblijf and is_rd and visit_index == 1:
        eff.start_timing_reference = "ABSOLUTE_TIME"
        eff.start_time_absolute_from = time(0, 0)
        
    return eff


# ---- Biological Compatibility & Helpers --------------------------------------

def _to_current_year(d: date) -> date:
    today = date.today()
    current_year = today.year
    try:
        return d.replace(year=current_year)
    except ValueError:
        if d.month == 2 and d.day == 29:
            return date(current_year, 2, 28)
        raise

def _unit_to_days(value: int | None, unit: str | None) -> int:
    if not value:
        return 0
    if not unit:
        return value
    u = unit.strip().lower()
    if u in {"week", "weeks", "weeken", "weken"}:
        return value * 7
    return value

def _normalize_family_name(name: str | None) -> str:
    if not name:
        return ""
    n = name.strip().lower()
    if "vleer" in n:
        return "vleermuis"
    if "zwaluw" in n:
        return "zwaluw"
    return n

def _same_family(a: Protocol, b: Protocol) -> bool:
    try:
        if a.species.family_id == b.species.family_id:
            return True
    except Exception:
        pass
    
    fam_obj = getattr(getattr(a, "species", None), "family", None)
    n1 = _normalize_family_name(getattr(fam_obj, "name", None))
    
    try:
        fam_obj_b = getattr(getattr(b, "species", None), "family", None)
        n2 = _normalize_family_name(getattr(fam_obj_b, "name", None))
    except Exception:
        n2 = ""
    return bool(n1) and n1 == n2

def _is_allowed_cross_family(a: Protocol, b: Protocol) -> bool:
    try:
        fam_a_obj = getattr(getattr(a, "species", None), "family", None)
        fam_a = _normalize_family_name(getattr(fam_a_obj, "name", None))
        
        fam_b_obj = getattr(getattr(b, "species", None), "family", None)
        fam_b = _normalize_family_name(getattr(fam_b_obj, "name", None))
    except Exception:
        return False

    pair = {fam_a, fam_b}
    allowed_pairs = [{"vleermuis", "zwaluw"}]
    return any(pair == allowed for allowed in allowed_pairs)

def _is_smp(p: Protocol) -> bool:
    try:
        fn = getattr(p, "function", None)
        name = getattr(fn, "name", "") or ""
        return name.startswith("SMP")
    except Exception:
        return False

def _check_bio_compatibility(p1: Protocol, p2: Protocol) -> bool:
    # SMP Gating
    smp1 = _is_smp(p1)
    smp2 = _is_smp(p2)
    
    if smp1 or smp2:
        if not (smp1 and smp2):
            return False
        return _same_family(p1, p2)

    # Exception: Rugstreeppad
    sp_name = getattr(getattr(p1, "species", None), "name", "")
    if sp_name == "Rugstreeppad":
        fn1 = getattr(p1, "function", None)
        fn2 = getattr(p2, "function", None)
        if fn1 and fn2 and fn1.id != fn2.id:
            return False

    if _same_family(p1, p2):
        return True
        
    return _is_allowed_cross_family(p1, p2)


# ---- Part of Day Logic -------------------------------------------------------

def _derive_part_options_base(protocol: Protocol) -> set[str] | None:
    """Return allowed part-of-day options based on timing reference only."""
    ref_start = protocol.start_timing_reference or ""
    ref_end = getattr(protocol, "end_timing_reference", None) or ""

    if ref_start == "DAYTIME":
        return {"Dag"}
    if ref_start == "ABSOLUTE_TIME":
        return {"Avond", "Ochtend"}

    if ref_start == "SUNSET" and ref_end == "SUNRISE":
        return {"Avond", "Ochtend"}
    if ref_start == "SUNSET":
        return {"Avond"}
    if ref_start == "SUNRISE":
        rel_min = protocol.start_time_relative_minutes
        if rel_min is not None and rel_min >= 0:
             return {"Dag"}
        return {"Ochtend"}
    if ref_start == "SUNSET_TO_SUNRISE":
        return {"Avond", "Ochtend"}
        
    return None

def _derive_part_of_day(protocol: Protocol) -> str | None:
    if getattr(protocol, "requires_morning_visit", False):
        return "Ochtend"
    if getattr(protocol, "requires_evening_visit", False):
        return "Avond"

    ref = protocol.start_timing_reference or ""
    if ref == "SUNRISE":
        if protocol.start_time_relative_minutes is not None and protocol.start_time_relative_minutes >= 0:
            return "Dag"
        else:
            return "Ochtend"
    if ref in {"SUNSET", "ABSOLUTE_TIME"}:
        return "Avond"
    if ref == "DAYTIME":
        return "Dag"
    return None


# ---- Visit Request Graph Model -----------------------------------------------

@dataclass
class VisitRequest:
    """Represents a single required visit occurrence (Node)."""
    protocol: Protocol
    visit_index: int
    window_from: date
    window_to: date
    pvw_id: int
    part_of_day_options: set[str] | None  # None means any
    
    compatible_request_ids: set[str] = field(default_factory=set)
    predecessor: tuple[str, int] | None = None

    @property
    def id(self) -> str:
        return f"p{self.protocol.id}_v{self.visit_index}"
    
    # helper for effective start calc during generation
    effective_window_from: date | None = None


def _generate_visit_requests(protocols: list[Protocol]) -> list[VisitRequest]:
    """Explode protocols into individual required visit occurrences."""
    requests: list[VisitRequest] = []
    
    req_map: dict[str, VisitRequest] = {}
    
    for p in protocols:
        if not p.visit_windows:
            continue
            
        windows = sorted(p.visit_windows, key=lambda w: w.visit_index)
        prev_request: VisitRequest | None = None
        
        min_gap_days = _unit_to_days(
            p.min_period_between_visits_value, 
            p.min_period_between_visits_unit
        )
        
        req_morning = getattr(p, "requires_morning_visit", False)
        req_evening = getattr(p, "requires_evening_visit", False)
        base_parts = _derive_part_options_base(p)

        for i, w in enumerate(windows):
            wf = _to_current_year(w.window_from)
            wt = _to_current_year(w.window_to)
            
            if wf > wt:
                continue

            parts = set(base_parts) if base_parts is not None else None
            
            # Legacy logic: enforce morning/evening flags mostly on V1
            if w.visit_index == 1:
                if req_morning:
                    if parts is None: parts = {"Ochtend"}
                    else: parts.intersection_update({"Ochtend"})
                if req_evening:
                    if parts is None: parts = {"Avond"}
                    else: parts.intersection_update({"Avond"})
            
            if not parts and base_parts:
                parts = base_parts

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
            
            requests.append(req)
            req_map[req.id] = req
            prev_request = req

    # Propagate effective starts
    for r in requests:
        wd_start = r.window_from
        if r.predecessor:
            pred_id, gap = r.predecessor
            pred = req_map[pred_id]
            pred_eff = pred.effective_window_from or pred.window_from
            min_valid = pred_eff + timedelta(days=gap)
            if min_valid > wd_start:
                wd_start = min_valid
        
        r.effective_window_from = wd_start

    return requests


def _build_compatibility_graph(requests: list[VisitRequest]) -> None:
    n = len(requests)
    for i in range(n):
        for j in range(i + 1, n):
            r1 = requests[i]
            r2 = requests[j]
            
            if _are_compatible(r1, r2):
                r1.compatible_request_ids.add(r2.id)
                r2.compatible_request_ids.add(r1.id)

def _are_compatible(r1: VisitRequest, r2: VisitRequest) -> bool:
    if r1.protocol.id == r2.protocol.id:
        return False

    if not _check_bio_compatibility(r1.protocol, r2.protocol):
        return False
        
    overlap = _overlap_days(
        r1.window_from, r1.window_to,
        r2.window_from, r2.window_to
    )
    if overlap < MIN_EFFECTIVE_WINDOW_DAYS:
        return False
        
    if not _check_part_intersection(r1.part_of_day_options, r2.part_of_day_options):
        return False
        
    return True

def _overlap_days(start1: date, end1: date, start2: date, end2: date) -> int:
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    delta = (overlap_end - overlap_start).days
    return delta if delta > 0 else 0

def _check_part_intersection(set1: set[str] | None, set2: set[str] | None) -> bool:
    if set1 is None or set2 is None:
        return True
    return not set1.isdisjoint(set2)


# ---- Misc Helpers ------------------------------------------------------------

def _select_most_restrictive_precipitation(options: list[str]) -> str | None:
    if not options:
        return None

    scored: list[tuple[str, int | None]] = []
    for value in options:
        norm = value.strip().lower()
        rank = _PRECIPITATION_PRIORITY.get(norm)
        scored.append((value, rank))

    known = [item for item in scored if item[1] is not None]
    if known:
        return max(known, key=lambda item: item[1])[0]

    return sorted(options, key=lambda s: (len(s), s))[0]


def calculate_visit_props(
    protocols: list[Protocol], 
    part_of_day: str | None, 
    reference_date: date | None = None,
    visit_indices: dict[int, int] | None = None
) -> tuple[int | None, str | None]:
    """Calculate duration (minutes) and start time text based on protocols and part of day."""

    effective_timings: list[EffectiveTiming] = []
    for p in protocols:
        v_idx = visit_indices.get(p.id) if visit_indices else None
        eff = _get_effective_timing(p, visit_index=v_idx, part_of_day=part_of_day)
        effective_timings.append(eff)

    durations = [
        t.visit_duration_hours for t in effective_timings if t.visit_duration_hours is not None
    ]
    duration_min = int(max(durations) * 60) if durations else None

    # Logic for Evening/Absolute scenarios
    use_improved_logic = False
    all_absolute = all(t.start_timing_reference == "ABSOLUTE_TIME" for t in effective_timings)
    mixed_absolute_sunset = False
    
    if not all_absolute and part_of_day == "Avond" and reference_date:
        refs = {t.start_timing_reference for t in effective_timings}
        if refs <= {"ABSOLUTE_TIME", "SUNSET"}:
             mixed_absolute_sunset = True
             
    if all_absolute or mixed_absolute_sunset:
        use_improved_logic = True
        
        starts = []
        ends = []
        
        for t in effective_timings:
            p_start_min = None
            if t.start_timing_reference == "ABSOLUTE_TIME" and t.start_time_absolute_from:
                 tm = t.start_time_absolute_from
                 hours = tm.hour if hasattr(tm, 'hour') else 0
                 minutes = tm.minute if hasattr(tm, 'minute') else 0
                 minutes_total = hours * 60 + minutes
                 
                 if minutes_total < 600:
                     minutes_total += 1440
                 p_start_min = minutes_total

            elif mixed_absolute_sunset and t.start_timing_reference == "SUNSET" and reference_date:
                 m = reference_date.month
                 sunset_min = 20 * 60 
                 if m == 7: sunset_min = 22 * 60
                 elif m == 8: sunset_min = 21 * 60
                 elif m == 9: sunset_min = 20 * 60
                 
                 rel = t.start_time_relative_minutes or 0
                 p_start_min = sunset_min + rel
                 
                 if p_start_min < 600: 
                     p_start_min += 1440
            
            if p_start_min is not None:
                starts.append(p_start_min)
                dur = (t.visit_duration_hours or 0) * 60
                ends.append(p_start_min + dur)
                
        if starts and ends:
            min_start = min(starts)
            max_end = max(ends)
            span = int(max_end - min_start)
            if duration_min is not None:
                duration_min = max(duration_min, span)
            else:
                duration_min = span

    def derive_end_time_minutes(p: Protocol) -> int | None:
        ref = p.end_timing_reference or ""
        rel = p.end_time_relative_minutes or 0
        if ref == "SUNRISE":
            return -rel
        return None

    def derive_start_time_minutes(p: Protocol) -> int | None:
        ref = p.start_timing_reference or ""
        rel = p.start_time_relative_minutes or 0
        if ref == "SUNRISE":
            return -rel
        if ref == "SUNSET":
            return rel
        return None

    # Morning/Evening refinements
    calc_start_for_duration: int | None = None
    end_candidates = [
        derive_end_time_minutes(p)
        for p in protocols
        if derive_end_time_minutes(p) is not None
    ]
    start_candidates = [
        derive_start_time_minutes(p)
        for p in protocols
        if derive_start_time_minutes(p) is not None
    ]
    
    starts_from_end_minus_duration: list[int] = []
    for p in protocols:
        end_m = derive_end_time_minutes(p)
        dur_h = getattr(p, "visit_duration_hours", None)
        if end_m is not None and dur_h is not None:
            starts_from_end_minus_duration.append(int(end_m - int(dur_h * 60)))

    if part_of_day == "Ochtend" and end_candidates:
        all_start_candidates = start_candidates + starts_from_end_minus_duration
        if all_start_candidates:
            calc_start_for_duration = int(min(all_start_candidates))
            latest_end = int(max(end_candidates))
            new_duration = int(max(0, latest_end - calc_start_for_duration))
            duration_min = new_duration

    start_text: str | None = None

    if part_of_day == "Ochtend" and calc_start_for_duration is not None:
        min_to_sunrise = calc_start_for_duration
        hours_before = abs(min_to_sunrise) / 60.0
        h_str = f"{hours_before:g}".replace(".", ",")
        start_text = f"{h_str} uur voor zonsopkomst"
        return duration_min, start_text

    # Default fallback text logic (ported)
    # Store candidates as tuples: (sort_key_minutes, text_str)
    # Sort key should use the same logic as duration calculation (wrap < 600 to +1440)
    text_candidates: list[tuple[float, str]] = []
    
    # Re-loop to pick text
    for i, p in enumerate(protocols):
        eff = effective_timings[i]
        
        # Override text for exceptions?
        # MV exception for Start Text
        fn = getattr(p, "function", None)
        sp = getattr(p, "species", None)
        fam = getattr(getattr(p, "species", None), "family", None)
        
        is_mv = (sp.abbreviation == "MV" or sp.name == "MV") if sp else False
        is_paarverblijf = (fn.name == "Paarverblijf") if fn else False
        
        if is_mv and is_paarverblijf and part_of_day == "Avond":
             text_candidates.append((0, "Zonsondergang")) # Priority sort? 
             continue
        if is_mv and is_paarverblijf and part_of_day == "Ochtend":
             text_candidates.append((0, "3 uur voor zonsopgang")) 
             continue
             
        # Vlinder Exception
        if fam and getattr(fam, "name", "") == "Vlinder":
             text_candidates.append((0, "Tussen 10:00 en 15:00 starten (evt. om 09:00 starten als het dan al 22 graden is en zonnig)"))
             continue

        if eff.start_timing_reference == "ABSOLUTE_TIME" and eff.start_time_absolute_from:
             tm = eff.start_time_absolute_from
             hours = tm.hour
             minutes = tm.minute
             minutes_total = hours * 60 + minutes
             if minutes_total < 600:
                 minutes_total += 1440
             
             t_str = tm.strftime("%H:%M")
             text_candidates.append((minutes_total, t_str))
             
        elif eff.start_timing_reference == "SUNSET":
             rel = eff.start_time_relative_minutes or 0
             # Estimate sort key for sunset: 20:00 (1200 min) base is decent
             # This is just for sorting relative to absolute.
             sort_key = 1200 + rel 
             if sort_key < 600: sort_key += 1440

             if rel == 0:
                 text_candidates.append((sort_key, "Zonsondergang"))
             elif rel > 0:
                 h_str = f"{rel/60.0:g}".replace(".", ",")
                 text_candidates.append((sort_key, f"{h_str} uur na zonsondergang"))
             else:
                 h_str = f"{abs(rel)/60.0:g}".replace(".", ",")
                 text_candidates.append((sort_key, f"{h_str} uur voor zonsondergang"))
        elif eff.start_timing_reference == "SUNRISE":
             rel = eff.start_time_relative_minutes or 0
             # Estimate sort key for sunrise: 06:00 (360 min) base?
             # But usually Ochtend. 
             # Let's say Sunrise = 06:00 = 360.
             sort_key = 360 + rel
             
             if rel == 0:
                 text_candidates.append((sort_key, "Zonsopkomst"))
             elif rel > 0:
                 h_str = f"{rel/60.0:g}".replace(".", ",")
                 text_candidates.append((sort_key, f"{h_str} uur na zonsopkomst"))
             else:
                 h_str = f"{abs(rel)/60.0:g}".replace(".", ",")
                 text_candidates.append((sort_key, f"{h_str} uur voor zonsopkomst"))
                 
    # Pick candidate with minimal sort key (earliest time)
    if text_candidates:
        # Sort by key (minutes)
        text_candidates.sort(key=lambda x: x[0])
        start_text = text_candidates[0][1]

    return duration_min, start_text

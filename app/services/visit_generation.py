from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from uuid import uuid4
import os
import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.species import Species
from app.models.visit import Visit


_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}
# Use uvicorn's error logger so messages always appear in console
_logger = logging.getLogger("uvicorn.error")

# Minimum acceptable effective window length (days) for a combined bucket
MIN_EFFECTIVE_WINDOW_DAYS = int(os.getenv("MIN_EFFECTIVE_WINDOW_DAYS", "14"))
# Note: visit priority is set when a window is tight (<= MIN_EFFECTIVE_WINDOW_DAYS)


def _subset_for_threshold(
    items: list[tuple[date, date, Protocol, set[str] | None]],
    threshold_days: int,
) -> list[tuple[date, date, Protocol, set[str] | None]] | None:
    """Find a smallest-removal subset whose common window meets threshold.

    Args:
        items: Per-protocol windows within a bucket as (from, to, protocol, parts).
        threshold_days: Minimum required length for the common window.

    Returns:
        A list of kept items meeting the threshold (preferring larger resulting window
        among same removal count), or None if impossible.
    """

    from itertools import combinations

    n = len(items)
    for remove_k in range(0, n + 1):
        best_len = -1
        best_choice: list[tuple[date, date, Protocol, set[str] | None]] | None = None
        for keep_idxs in combinations(range(n), n - remove_k):
            kept = [items[i] for i in keep_idxs]
            new_from = max(wf for (wf, wt, _p, _pa) in kept)
            new_to = min(wt for (wf, wt, _p, _pa) in kept)
            if new_from > new_to:
                continue
            window_len = (new_to - new_from).days
            if window_len >= threshold_days and window_len > best_len:
                best_len = window_len
                best_choice = kept
        if best_choice is not None:
            return best_choice
    return None


def _normalize_tight_buckets(drafts: list[dict], threshold_days: int) -> list[dict]:
    """Normalize buckets by splitting tight ones into best subset + singles.

    Each draft must contain:
      - from_date, to_date, protocols, chosen_part_of_day, visit_index
      - meta.per_proto_windows: list[(protocol, (wf, wt))]
    """

    out: list[dict] = []
    for d in drafts:
        wf, wt = d["from_date"], d["to_date"]
        protos: list[Protocol] = d["protocols"]
        if (wt - wf).days >= threshold_days or len(protos) <= 1:
            out.append(d)
            continue
        items: list[tuple[date, date, Protocol, set[str] | None]] = [
            (it_wf, it_wt, p, None)
            for (p, (it_wf, it_wt)) in d["meta"]["per_proto_windows"]
        ]
        best = _subset_for_threshold(items, threshold_days)
        if best is None:
            # all singles
            for it_wf, it_wt, p, _pa in items:
                if it_wf <= it_wt:
                    out.append(
                        {
                            "from_date": it_wf,
                            "to_date": it_wt,
                            "protocols": [p],
                            "chosen_part_of_day": d.get("chosen_part_of_day"),
                            "visit_index": d.get("visit_index"),
                        }
                    )
            continue
        # emit best combined
        best_from = max(it_wf for (it_wf, it_wt, _p, _pa) in best)
        best_to = min(it_wt for (it_wf, it_wt, _p, _pa) in best)
        out.append(
            {
                "from_date": best_from,
                "to_date": best_to,
                "protocols": [p for (_wf, _wt, p, _pa) in best],
                "chosen_part_of_day": d.get("chosen_part_of_day"),
                "visit_index": d.get("visit_index"),
            }
        )
        # emit singles for removed
        kept_set = {id(p) for (_wf, _wt, p, _pa) in best}
        for it_wf, it_wt, p, _pa in items:
            if id(p) not in kept_set and it_wf <= it_wt:
                out.append(
                    {
                        "from_date": it_wf,
                        "to_date": it_wt,
                        "protocols": [p],
                        "chosen_part_of_day": d.get("chosen_part_of_day"),
                        "visit_index": d.get("visit_index"),
                    }
                )
    return out


def _enforce_sequence_feasibility(visits: list[dict]) -> list[dict]:
    """Offline pass to enforce per-protocol min-gap feasibility across indices.

    For each protocol, walk visits by visit_index;
    if the next index own window (shifted per protocol) adjusted by min-gap becomes
    invalid, demote the current protocol to a single and optionally create a next single.
    """

    # Helper: build per-protocol map of entries by visit_index
    proto_map: dict[int, list[dict]] = defaultdict(list)
    for entry in visits:
        vidx = entry.get("visit_index")
        for p in entry["protocols"]:
            proto_map[p.id].append(entry)
    for entries in proto_map.values():
        entries.sort(key=lambda e: e.get("visit_index") or 0)

    updated: list[dict] = visits[:]  # shallow copy of list

    for proto_id, entries in proto_map.items():
        for i in range(len(entries)):
            curr = entries[i]
            vidx = curr.get("visit_index") or 1
            p = next((pp for pp in curr["protocols"] if pp.id == proto_id), None)
            if p is None:
                continue
            # find next window for this protocol
            w2 = next((w for w in p.visit_windows if w.visit_index == vidx + 1), None)
            if w2 is None:
                continue
            proto_days2 = _unit_to_days(
                p.min_period_between_visits_value, p.min_period_between_visits_unit
            )
            off2 = (vidx) * (proto_days2 if proto_days2 else 0)
            cand_from2 = _to_current_year(w2.window_from) + timedelta(days=off2)
            cand_to2 = _to_current_year(w2.window_to)
            cand_from2 = max(
                cand_from2, curr["from_date"] + timedelta(days=(proto_days2 or 0))
            )
            # If infeasible, demote current protocol to single; keep next visit to be handled by normal flow
            if (
                cand_from2 > cand_to2
                or (cand_to2 - cand_from2).days < MIN_EFFECTIVE_WINDOW_DAYS
            ):
                # Remove p from current combined
                if len(curr["protocols"]) > 1:
                    curr["protocols"] = [
                        pp for pp in curr["protocols"] if pp.id != proto_id
                    ]
                    # Add a single for current using intersection with p's own window for this index
                    w_curr = next(
                        (w for w in p.visit_windows if w.visit_index == vidx), None
                    )
                    if w_curr is not None:
                        # Recompute shifted start for current index
                        proto_days_curr = _unit_to_days(
                            p.min_period_between_visits_value,
                            p.min_period_between_visits_unit,
                        )
                        off_curr = (vidx - 1) * (
                            proto_days_curr if proto_days_curr else 0
                        )
                        wf = _to_current_year(w_curr.window_from) + timedelta(
                            days=off_curr
                        )
                        wt = _to_current_year(w_curr.window_to)
                        sing_from = max(
                            wf, curr["from_date"]
                        )  # keep inside bucket window
                        sing_to = min(wt, curr["to_date"])  # keep inside bucket window
                        if sing_from <= sing_to:
                            updated.append(
                                {
                                    "from_date": sing_from,
                                    "to_date": sing_to,
                                    "protocols": [p],
                                    "chosen_part_of_day": curr.get(
                                        "chosen_part_of_day"
                                    ),
                                    "visit_index": vidx,
                                }
                            )
                # Optionally create next single if still possible
                if cand_from2 <= cand_to2:
                    updated.append(
                        {
                            "from_date": cand_from2,
                            "to_date": cand_to2,
                            "protocols": [p],
                            "chosen_part_of_day": None,
                            "visit_index": vidx + 1,
                        }
                    )
    # Drop any empty combined entries created by removals
    updated = [e for e in updated if e.get("protocols")]
    return updated


def _windows_overlap(a: tuple[date, date], b: tuple[date, date]) -> bool:
    """Return True if two [from, to] date windows overlap.

    Args:
        a: Tuple of (from_date, to_date) inclusive.
        b: Tuple of (from_date, to_date) inclusive.

    Returns:
        True when the two windows overlap, otherwise False.
    """

    return not (a[1] < b[0] or b[1] < a[0])


def _connected_components_by_overlap(
    items: list[tuple[int, tuple[date, date]]],
) -> list[list[int]]:
    """Build connected components where edges exist if windows overlap.

    Args:
        items: list of (local_index, (from_date, to_date)).

    Returns:
        A list of components; each component is a list of local indexes.
    """

    n = len(items)
    adjacency: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if _windows_overlap(items[i][1], items[j][1]):
                adjacency[i].add(j)
                adjacency[j].add(i)

    seen: set[int] = set()
    components: list[list[int]] = []
    for i in range(n):
        if i in seen:
            continue
        stack = [i]
        component: list[int] = []
        seen.add(i)
        while stack:
            u = stack.pop()
            component.append(u)
            for v in adjacency[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        components.append(component)
    return components


# ---- Exception rules scaffolding -------------------------------------------------


def _same_family(a: Protocol, b: Protocol) -> bool:
    """Return True if two protocols belong to the same species family.

    Args:
        a: First protocol.
        b: Second protocol.

    Returns:
        True if species family is equal, otherwise False. When family info is missing, returns False.
    """

    try:
        return a.species.family_id == b.species.family_id
    except Exception:
        return False


def _normalize_family_name(name: str | None) -> str:
    """Normalize family name for matching (case-insensitive, handle common variants).

    Collapses Dutch variants like "Vleermuis"/"Vleermuizen" to a single key.
    """

    if not name:
        return ""
    n = name.strip().lower()
    if "vleer" in n:  # matches vleermuis/vleermuizen
        return "vleermuis"
    if "zwaluw" in n:  # matches zwaluw/zwaluwen
        return "zwaluw"
    return n


def _same_family_name(a: Protocol, b: Protocol) -> bool:
    """Return True if two protocols share the same species family name.

    Falls back to False if names are unavailable.
    """

    try:
        name_a = _normalize_family_name(getattr(a.species.family, "name", None))
        name_b = _normalize_family_name(getattr(b.species.family, "name", None))
        return bool(name_a) and name_a == name_b
    except Exception:
        return False


def _is_allowed_cross_family(a: Protocol, b: Protocol) -> bool:
    """Determine if a specific cross-family combination is allowed.

    Default implementation returns False (no cross-family grouping). Extend later with
    a curated allowlist.
    """

    try:
        fam_a = _normalize_family_name(getattr(a.species.family, "name", None))
        fam_b = _normalize_family_name(getattr(b.species.family, "name", None))
    except Exception:
        return False

    pair = {fam_a, fam_b}
    allowed_pairs = [{"vleermuis", "zwaluw"}]
    return any(pair == allowed for allowed in allowed_pairs)


def _functions_in_allowed_set(function_ids: set[int], allowed: set[int]) -> bool:
    """Check whether a set of functions is a subset of an allowed set."""

    return function_ids.issubset(allowed)


def _allow_together(a: Protocol, b: Protocol) -> bool:
    """Compatibility check whether two protocols may be grouped.

    This is the main hook for future exception rules. Current defaults:
      - Allow only same-family groupings by default (by id or by family name).
      - Allow specific cross-family exceptions (e.g., Vleermuis ↔ Zwaluw).

    Args:
        a: First protocol.
        b: Second protocol.

    Returns:
        True if protocols may be grouped together.
    """

    if _same_family(a, b) or _same_family_name(a, b):
        return True
    return _is_allowed_cross_family(a, b)


def _apply_custom_recipe_if_any(
    _protos: list[Protocol], _visit_index: int
) -> list[list[Protocol]] | None:
    """Optional custom recipe for specific family/function combinations.

    Given the selected protocols and a visit_index, return an ordered list of protocol
    buckets if a custom sequencing rule applies. Returning None means no custom recipe
    is applied; the generic bucketing logic should be used instead.

    Current implementation returns None (placeholder). Extend later to support rules like:
      - For family A with functions {B, C}: [[B@1], [B@2, C@1], [C@2]].
    """

    return None


async def _next_visit_nr(db: AsyncSession, cluster_id: int) -> int:
    stmt = (
        select(Visit.visit_nr)
        .where(Visit.cluster_id == cluster_id)
        .order_by(Visit.visit_nr.desc())
    )
    row = (await db.execute(stmt)).first()
    return (row[0] or 0) + 1 if row else 1


def _derive_part_of_day(protocol: Protocol) -> str | None:
    """Derive part of day string from protocol flags and timing reference.

    Overrides:
      - If requires_morning_visit: "Ochtend"
      - If requires_evening_visit: "Avond"

    Otherwise based on start_timing_reference:
      - SUNRISE -> "Ochtend"
      - SUNSET or ABSOLUTE_TIME -> "Avond"
      - DAYTIME -> "Dag"
    """

    if getattr(protocol, "requires_morning_visit", False):
        return "Ochtend"
    if getattr(protocol, "requires_evening_visit", False):
        return "Avond"

    ref = protocol.start_timing_reference or ""
    if ref == "SUNRISE":
        return "Ochtend"
    if ref in {"SUNSET", "ABSOLUTE_TIME"}:
        return "Avond"
    if ref == "DAYTIME":
        return "Dag"
    return None


def _derive_part_options(protocol: Protocol) -> set[str] | None:
    """Return allowed part-of-day options for a protocol.

    Hard constraints take precedence; otherwise infer from timing references.
    Preference for later selection is handled outside this function.
    """

    if getattr(protocol, "requires_morning_visit", False):
        return {"Ochtend"}
    if getattr(protocol, "requires_evening_visit", False):
        return {"Avond"}

    ref_start = protocol.start_timing_reference or ""
    ref_end = getattr(protocol, "end_timing_reference", None) or ""

    if ref_start == "DAYTIME":
        return {"Dag"}
    if ref_start == "ABSOLUTE_TIME":
        # If absolute start time is present and clearly in the morning (<12), pick morning, else evening
        if (
            getattr(protocol, "start_time_absolute_from", None) is not None
            and protocol.start_time_absolute_from.hour < 12
        ):
            return {"Ochtend"}
        return {"Avond"}

    # Overnight window from sunset to sunrise allows both evening and (next) morning
    if ref_start == "SUNSET" and ref_end == "SUNRISE":
        return {"Avond", "Ochtend"}
    if ref_start == "SUNSET":
        return {"Avond"}
    if ref_start == "SUNRISE":
        return {"Ochtend"}

    return None


def _derive_start_time_minutes(protocol: Protocol) -> int | None:
    """Compute start time in minutes relative to the timing reference.

    When start_timing_reference is SUNRISE, subtract visit_duration_hours
    (converted to minutes) from start_time_relative_minutes.
    Otherwise, return start_time_relative_minutes as-is.
    """

    ref = protocol.start_timing_reference or ""
    rel = protocol.start_time_relative_minutes
    if rel is None:
        return None
    if ref == "SUNRISE":
        duration_h = protocol.visit_duration_hours or 0
        return int(rel - duration_h * 60)
    return rel


def _derive_start_time_text(protocol: Protocol) -> str | None:
    """Build Dutch textual description for start time.

    Mapping:
      - SUNRISE -> "Zonsopkomst" or "<X> uur voor/na zonsopkomst" if relative minutes present
      - SUNSET -> "Zonsondergang" or relative form to zonsondergang
      - DAYTIME -> "Overdag"
      - ABSOLUTE_TIME -> absolute clock time if available
    For relative minutes: use hours with .5 steps (e.g., 90 -> 1,5 uur).
    """

    ref = protocol.start_timing_reference or ""
    rel = protocol.start_time_relative_minutes

    def fmt_hours(minutes: int) -> str:
        # Round to nearest 30 minutes for nicer text
        sign = -1 if minutes < 0 else 1
        m = abs(minutes)
        half_steps = round(m / 30)
        value_h = half_steps * 0.5
        # Use comma for half hours in Dutch
        text = f"{int(value_h)}" if value_h.is_integer() else f"{int(value_h)} ,5"
        # fix space before comma
        text = text.replace(" ", "")
        return ("-" if sign < 0 else "") + text

    if ref == "DAYTIME":
        return "Overdag"

    if ref == "ABSOLUTE_TIME":
        if protocol.start_time_absolute_from is not None:
            return protocol.start_time_absolute_from.strftime("%H:%M")
        return None

    if ref in {"SUNRISE", "SUNSET"}:
        # base label
        base = "zonsopkomst" if ref == "SUNRISE" else "zonsondergang"
        if rel in (None, 0):
            return "Zonsopkomst" if ref == "SUNRISE" else "Zonsondergang"
        hours = fmt_hours(rel)
        direction = "na" if rel > 0 else "voor"
        # Remove leading '-' from hours and use Dutch comma
        hours_clean = hours.lstrip("-").replace(".", ",")
        return f"{hours_clean} uur {direction} {base}"

    return None


def derive_start_time_text_for_visit(
    part_of_day: str | None, start_time_minutes: int | None
) -> str | None:
    """Derive Dutch start time text from persisted visit fields.

    Args:
        part_of_day: One of "Ochtend", "Avond", "Dag" or None.
        start_time_minutes: Relative minutes to the timing reference (can be negative).

    Returns:
        Human-readable Dutch description, or None when not derivable.
    """

    if part_of_day == "Dag":
        return "Overdag"
    if start_time_minutes in (None,):
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

    return None


def _to_current_year(d: date) -> date:
    """Return the same month/day as ``d`` but in the current calendar year.

    Handles leap day by clamping to Feb 28 in non-leap years.
    """

    today_year = date.today().year
    try:
        return d.replace(year=today_year)
    except ValueError:
        # Feb 29 -> Feb 28 for non-leap years
        if d.month == 2 and d.day == 29:
            return date(today_year, 2, 28)
        raise


def _unit_to_days(value: int | None, unit: str | None) -> int:
    """Convert period value+unit to days; unknown unit treated as days.

    Supports common variants for days/weeks in English/Dutch.
    """

    if not value:
        return 0
    if not unit:
        return value
    u = unit.strip().lower()
    if u in {"week", "weeks", "weeken", "weken"}:
        return value * 7
    # default assume days
    return value


def _extract_whitelisted_remarks(texts: list[str]) -> list[str]:
    """Extract a unique, ordered list of whitelisted planning remarks.

    Only retain phrases from a curated allowlist to avoid duplicating
    information that is already stored as structured fields (e.g. durations).
    """

    if not texts:
        return []

    # Allowlist; compare case-insensitively using substring contains
    allowlist: list[str] = [
        "1x in de kraamperiode",
        "eventueel 1 ochtend",
        "ten minste 1 ochtend",
        "enkel ochtend bezoeken",
        "1 ochtend",
        "relatief warme avonden, bij voorkeur na regen of een weersomslag",
        "fijnmazig schepnet (ravon-type) mee. ook letten op koren en aanwezige individuen. platen neerleggen in plangebied. vuistregel circa 10 platen per 100m geschikt leefgebied.",
        "zo mogelijk 1 ochtend",
        "1 ronde in juni",
        "'s avonds",
        "'s ochtends",
        "geen vrieskou; bezoeken uitvoeren met wbc; periodiek afspelen geluid ransuil.",
        "in omgeving van kraamgroepen en mannenverblijven (zie de bij het protocol gepubliceerde kaart)",
        "bij aantreffen verblijf binnen 3 dagen uitvliegtelling.",
        "6 weken in de periode 15 feb-1 mei of 3 weken in de periode 1 aug-1 okt",
        "1 x per week in de periode",
        "1 x in de kraamperiode",
        "1x buiten kraamperiode",
        "bij voorkeur niet na (hevige) regenbuien",
        "min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (>50% bewolking)",
        "minimaal 10 dagen na laatste massawinterverblijfbezoek",
        "1 x in de periode 1 aug - 1 okt",
    ]

    found: list[str] = []
    seen: set[str] = set()
    texts_norm = [t.lower() for t in texts if t]
    for phrase in allowlist:
        p = phrase.lower()
        if any(p in t for t in texts_norm):
            if phrase not in seen:
                seen.add(phrase)
                found.append(phrase)
    return found


async def generate_visits_for_cluster(
    db: AsyncSession,
    cluster: Cluster,
    function_ids: list[int],
    species_ids: list[int],
) -> tuple[list[Visit], list[str]]:
    """Generate visits for a cluster based on selected functions and species.

    This is an append-only operation: existing visits are left intact.
    The algorithm consists of two phases:
      1) Greedy "tightest-first" bucketing of protocol windows with compatibility and
         minimum effective window checks (Avond/Ochtend/Dag parts intersected).
      2) A completion pass that ensures each protocol visit_index has at least one
         planned visit; if a window has no planned occurrence, we add a single visit
         within its own window (respecting min-gap to the next planned when possible).

    Returns:
        (visits, warnings): The created Visit ORM objects and user-facing warnings
        in Dutch for any protocol windows that could not be planned.
    """

    if _DEBUG_VISIT_GEN:
        _logger.info(
            "visit_gen start cluster=%s functions=%s species=%s",
            getattr(cluster, "id", None),
            function_ids,
            species_ids,
        )

    warnings: list[str] = []

    if not function_ids or not species_ids:
        return [], warnings

    # Fetch all protocols for selected pairs and their windows (eager-load windows)
    stmt: Select[tuple[Protocol]] = (
        select(Protocol)
        .where(
            Protocol.function_id.in_(function_ids), Protocol.species_id.in_(species_ids)
        )
        .options(
            selectinload(Protocol.visit_windows),
            selectinload(Protocol.species).selectinload(Species.family),
            selectinload(Protocol.function),
        )
    )
    protocols: list[Protocol] = (await db.execute(stmt)).scalars().unique().all()

    if not protocols:
        return [], warnings

    # Windows loaded via selectinload

    # 1) Precompute shifted windows per protocol and tightness key
    #    Shift only the start per visit_index using the protocol's own min period;
    #    keep window_to fixed in the current year.
    proto_id_to_protocol: dict[int, Protocol] = {p.id: p for p in protocols}
    proto_windows: dict[int, list[tuple[int, date, date, set[str] | None]]] = {}
    for p in protocols:
        items: list[tuple[int, date, date, set[str] | None]] = []
        if p.visit_windows:
            for w in sorted(p.visit_windows, key=lambda w: w.visit_index):
                vidx = w.visit_index
                proto_days = _unit_to_days(
                    p.min_period_between_visits_value, p.min_period_between_visits_unit
                )
                offset_days = (vidx - 1) * (proto_days if proto_days else 0)
                wf = _to_current_year(w.window_from) + timedelta(days=offset_days)
                wt = _to_current_year(w.window_to)
                if wf <= wt:
                    items.append((vidx, wf, wt, _derive_part_options(p)))
        if items:
            proto_windows[p.id] = items

    def tightness_key(p: Protocol) -> tuple[int, date]:
        items = proto_windows.get(p.id, [])
        if not items:
            return (10_000, date.max)
        max_idx_item = max(items, key=lambda it: it[0])
        _, wf, wt, _ = max_idx_item
        length = (wt - wf).days
        earliest = min(it[1] for it in items)
        return (length, earliest)

    ordered = sorted([p for p in protocols if p.id in proto_windows], key=tightness_key)

    # 2) Buckets: greedy tightest-first placement
    #    Buckets maintain a running intersection window and part-of-day intersection.
    #    A protocol may be placed in a bucket only if:
    #      - family compatibility holds for all existing bucket protocols
    #      - intersection window is non-empty and >= MIN_EFFECTIVE_WINDOW_DAYS
    #      - parts-of-day intersection is None or non-empty
    #      - for visit_index > 1: start respects previous placement + min period
    class _Bucket:
        def __init__(
            self,
            wf: date,
            wt: date,
            parts: set[str] | None,
            first_proto: Protocol,
            vidx: int,
        ):
            self.from_date = wf
            self.to_date = wt
            self.parts = parts
            self.proto_ids: set[int] = {first_proto.id}
            self.last_from_by_proto: dict[int, date] = {first_proto.id: wf}

        def _inter(self, a: set[str] | None, b: set[str] | None) -> set[str] | None:
            if a is None and b is None:
                return None
            if a is None:
                return b
            if b is None:
                return a
            return a & b

        def candidate_accepts(
            self,
            p: Protocol,
            wf: date,
            wt: date,
            parts: set[str] | None,
            last_from_p: date | None,
            vidx: int,
            proto_days: int,
        ) -> tuple[bool, tuple[date, date], set[str] | None]:
            for pid in self.proto_ids:
                if not _allow_together(p, proto_id_to_protocol[pid]):
                    return (False, (self.from_date, self.to_date), self.parts)
            new_from = max(self.from_date, wf)
            new_to = min(self.to_date, wt)
            if new_from > new_to:
                return (False, (self.from_date, self.to_date), self.parts)
            if (new_to - new_from).days < MIN_EFFECTIVE_WINDOW_DAYS:
                return (False, (self.from_date, self.to_date), self.parts)
            # Enforce sequencing gap for visit_index > 1
            if vidx > 1 and last_from_p is not None:
                required_from = last_from_p + timedelta(days=(proto_days or 0))
                if new_from < required_from:
                    return (False, (self.from_date, self.to_date), self.parts)
            new_parts = self._inter(self.parts, parts)
            if new_parts is not None and len(new_parts) == 0:
                return (False, (self.from_date, self.to_date), self.parts)
            return (True, (new_from, new_to), new_parts)

        def place(
            self,
            p: Protocol,
            wf: date,
            wt: date,
            parts: set[str] | None,
            new_from: date,
            new_to: date,
            new_parts: set[str] | None,
        ):
            self.from_date = new_from
            self.to_date = new_to
            self.parts = new_parts
            self.proto_ids.add(p.id)
            self.last_from_by_proto[p.id] = new_from

    buckets: list[_Bucket] = []
    if ordered:
        first = ordered[0]
        for vidx, wf, wt, parts in proto_windows[first.id]:
            buckets.append(_Bucket(wf, wt, parts, first, vidx))

    for p in ordered[1:]:
        last_from_p: date | None = None
        for vidx, wf, wt, parts in proto_windows[p.id]:
            proto_days = _unit_to_days(
                p.min_period_between_visits_value, p.min_period_between_visits_unit
            )
            placed = False
            for b in sorted(buckets, key=lambda b: (b.to_date, b.from_date)):
                if p.id in b.proto_ids:
                    continue
                ok, (nf, nt), nparts = b.candidate_accepts(
                    p, wf, wt, parts, last_from_p, vidx, proto_days
                )
                if ok:
                    b.place(p, wf, wt, parts, nf, nt, nparts)
                    last_from_p = nf
                    placed = True
                    break
            if not placed:
                # Enforce gap when opening a new bucket for vidx>1
                adj_wf = wf
                if vidx > 1 and last_from_p is not None:
                    required_from = last_from_p + timedelta(days=(proto_days or 0))
                    adj_wf = max(wf, required_from)
                if adj_wf <= wt:
                    b = _Bucket(adj_wf, wt, parts, p, vidx)
                    buckets.append(b)
                    last_from_p = adj_wf

    # Emit visits from buckets
    # Each bucket becomes one visit with the bucket window and preferred part-of-day.
    visits_to_create: list[dict] = []
    for b in buckets:
        chosen_part = None
        if b.parts and len(b.parts) > 0:
            if "Avond" in b.parts:
                chosen_part = "Avond"
            elif "Ochtend" in b.parts:
                chosen_part = "Ochtend"
            elif "Dag" in b.parts:
                chosen_part = "Dag"
        visits_to_create.append(
            {
                "from_date": b.from_date,
                "to_date": b.to_date,
                "protocols": [proto_id_to_protocol[pid] for pid in sorted(b.proto_ids)],
                "chosen_part_of_day": chosen_part,
            }
        )

    # Coalesce duplicate windows (same from/to and part) by unioning protocols
    if visits_to_create:
        merged_map: dict[tuple[date, date, str | None], dict] = {}
        for v in visits_to_create:
            key = (v["from_date"], v["to_date"], v.get("chosen_part_of_day"))
            existing = merged_map.get(key)
            if existing is None:
                merged_map[key] = {
                    "from_date": v["from_date"],
                    "to_date": v["to_date"],
                    "chosen_part_of_day": v.get("chosen_part_of_day"),
                    "protocols": list(v["protocols"]),
                }
            else:
                existing_ids = {p.id for p in existing["protocols"]}
                for p in v["protocols"]:
                    if p.id not in existing_ids:
                        existing["protocols"].append(p)
                        existing_ids.add(p.id)
        visits_to_create = list(merged_map.values())

    # Completion pass: ensure each protocol has one planned visit per visit_index window
    # Match planned occurrences to windows without reusing the same planned date across windows.
    proto_to_planned_froms: dict[int, list[date]] = defaultdict(list)
    for entry in visits_to_create:
        for p in entry["protocols"]:
            proto_to_planned_froms[p.id].append(entry["from_date"])
    for pid, windows in proto_windows.items():
        p = proto_id_to_protocol[pid]
        win_list = sorted(
            windows, key=lambda it: it[0], reverse=True
        )  # (vidx,wf,wt,parts)
        planned = sorted(proto_to_planned_froms.get(pid, []))
        used: set[int] = set()  # indexes into planned that are assigned to a window
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "completion check proto=%s windows=%s planned=%s",
                getattr(p, "id", None),
                [
                    (vidx, wf.isoformat(), wt.isoformat())
                    for (vidx, wf, wt, _pa) in sorted(windows, key=lambda it: it[0])
                ],
                [d.isoformat() for d in planned],
            )
        proto_days = _unit_to_days(
            p.min_period_between_visits_value, p.min_period_between_visits_unit
        )
        for vidx, wf, wt, parts in win_list:
            # find an unused planned date within this window
            assign_idx = None
            for i, d in enumerate(planned):
                if i in used:
                    continue
                if wf <= d <= wt:
                    assign_idx = i
                    break
            if assign_idx is not None:
                used.add(assign_idx)
                continue
            # No planned found for this window: add one as early as feasible.
            # For first window, do not apply previous-gap. For later windows, apply min-gap
            # relative to the last assigned occurrence.
            candidate_from = wf
            prev_dates = [planned[i] for i in used if planned[i] <= candidate_from]
            prev = max(prev_dates) if prev_dates else None
            # Only enforce previous gap for visit_index > 1
            if vidx > 1 and prev is not None and proto_days:
                candidate_from = max(candidate_from, prev + timedelta(days=proto_days))
            if candidate_from > wt:
                msg = None
                try:
                    abbr = (
                        getattr(getattr(p, "species", None), "abbreviation", None)
                        or getattr(getattr(p, "species", None), "name", None)
                        or "onbekend"
                    )
                    fname = (
                        getattr(getattr(p, "function", None), "name", None)
                        or "onbekend"
                    )
                    msg = f"Het is niet gelukt om een bezoek voor {abbr} voor functie {fname} in te plannen."
                except Exception:
                    msg = "Het is niet gelukt om een bezoek in te plannen."
                warnings.append(msg)
                if _DEBUG_VISIT_GEN:
                    _logger.warning(
                        "cannot add required visit proto=%s vidx=%s earliest_from=%s > window_to=%s",
                        getattr(p, "id", None),
                        vidx,
                        candidate_from.isoformat(),
                        wt.isoformat(),
                    )
                continue
            nxt_candidates = [d for d in planned if d >= candidate_from]
            nxt = min(nxt_candidates) if nxt_candidates else None
            if (
                nxt is not None
                and proto_days
                and candidate_from + timedelta(days=proto_days) > nxt
            ):
                if _DEBUG_VISIT_GEN:
                    _logger.warning(
                        "gap violation risk proto=%s vidx=%s candidate_from=%s next_from=%s min_gap_days=%s",
                        getattr(p, "id", None),
                        vidx,
                        candidate_from.isoformat(),
                        nxt.isoformat(),
                        proto_days,
                    )
            # Clamp end before next planned visit start (consider ALL planned dates)
            candidate_to = wt
            nxt_candidates = [d for d in planned if d >= candidate_from]
            nxt = min(nxt_candidates) if nxt_candidates else None
            if nxt is not None:
                before_next = nxt - timedelta(days=1)
                if before_next >= candidate_from:
                    candidate_to = min(candidate_to, before_next)

            chosen_part = None
            if parts and len(parts) > 0:
                if "Avond" in parts:
                    chosen_part = "Avond"
                elif "Ochtend" in parts:
                    chosen_part = "Ochtend"
                elif "Dag" in parts:
                    chosen_part = "Dag"
            visits_to_create.append(
                {
                    "from_date": candidate_from,
                    "to_date": candidate_to,
                    "protocols": [p],
                    "chosen_part_of_day": chosen_part,
                }
            )
            if _DEBUG_VISIT_GEN:
                _logger.info(
                    "completion add proto=%s vidx=%s added=(%s,%s)",
                    getattr(p, "id", None),
                    vidx,
                    candidate_from.isoformat(),
                    candidate_to.isoformat(),
                )
            # insert into planned and mark used
            # keep planned sorted
            insert_pos = 0
            while insert_pos < len(planned) and planned[insert_pos] < candidate_from:
                insert_pos += 1
            planned.insert(insert_pos, candidate_from)
            # find index of inserted element (first occurrence of candidate_from at/after insert_pos)
            assign_idx = planned.index(candidate_from, insert_pos)
            used.add(assign_idx)

    # Re-coalesce duplicates after additions
    if visits_to_create:
        merged_map2: dict[tuple[date, date, str | None], dict] = {}
        for v in visits_to_create:
            key = (v["from_date"], v["to_date"], v.get("chosen_part_of_day"))
            existing = merged_map2.get(key)
            if existing is None:
                merged_map2[key] = {
                    "from_date": v["from_date"],
                    "to_date": v["to_date"],
                    "chosen_part_of_day": v.get("chosen_part_of_day"),
                    "protocols": list(v["protocols"]),
                }
            else:
                existing_ids = {p.id for p in existing["protocols"]}
                for p in v["protocols"]:
                    if p.id not in existing_ids:
                        existing["protocols"].append(p)
                        existing_ids.add(p.id)
        visits_to_create = list(merged_map2.values())

    # Order by start date to assign visit_nr
    visits_to_create.sort(key=lambda v: v["from_date"])

    created: list[Visit] = []
    series_group_id = str(uuid4())
    next_nr = await _next_visit_nr(db, cluster.id)
    for v in visits_to_create:
        protos: list[Protocol] = v["protocols"]
        # strictest constraints
        min_temp = max(
            (
                p.min_temperature_celsius
                for p in protos
                if p.min_temperature_celsius is not None
            ),
            default=None,
        )
        max_wind = min(
            (p.max_wind_force_bft for p in protos if p.max_wind_force_bft is not None),
            default=None,
        )
        # precipitation: pick the most restrictive qualitative by shortest string (fallback to first)
        precip_options = [p.max_precipitation for p in protos if p.max_precipitation]
        precip = (
            sorted(precip_options, key=lambda s: (len(s), s))[0]
            if precip_options
            else None
        )
        # duration: take max in hours -> minutes
        durations = [
            p.visit_duration_hours for p in protos if p.visit_duration_hours is not None
        ]
        duration_min = int(max(durations) * 60) if durations else None
        # start time: earliest derived start among protos
        derived_starts = [
            _derive_start_time_minutes(p)
            for p in protos
            if _derive_start_time_minutes(p) is not None
        ]
        start_time = min(derived_starts) if derived_starts else None
        # part of day: prefer chosen bucket value, else first derived non-null
        chosen_bucket_part = v.get("chosen_part_of_day")
        part_values = [
            _derive_part_of_day(p) for p in protos if _derive_part_of_day(p) is not None
        ]
        part_of_day = chosen_bucket_part or (part_values[0] if part_values else None)
        # start time text: pick the earliest by minutes, but rebuild text using that protocol
        text_candidates: list[tuple[int, str]] = []
        for p in protos:
            m = _derive_start_time_minutes(p)
            t = _derive_start_time_text(p)
            if m is not None and t is not None:
                text_candidates.append((m, t))
        start_time_text = min(text_candidates)[1] if text_candidates else None
        # remarks: select unique whitelisted phrases only
        remarks_texts = [
            p.visit_conditions_text for p in protos if p.visit_conditions_text
        ]
        extracted = _extract_whitelisted_remarks(remarks_texts)
        remarks_field = " | ".join(extracted) if extracted else None

        # derive boolean requirement flags (true if any protocol requires it)
        requires_morning = any(
            getattr(p, "requires_morning_visit", False) for p in protos
        )
        requires_evening = any(
            getattr(p, "requires_evening_visit", False) for p in protos
        )
        requires_june = any(getattr(p, "requires_june_visit", False) for p in protos)
        requires_maternity = any(
            getattr(p, "requires_maternity_period_visit", False) for p in protos
        )

        # union of functions/species across combined protos
        function_ids_set = sorted({p.function_id for p in protos})
        species_ids_set = sorted({p.species_id for p in protos})

        visit = Visit(
            cluster_id=cluster.id,
            group_id=series_group_id,
            required_researchers=None,
            visit_nr=next_nr,
            from_date=v["from_date"],
            to_date=v["to_date"],
            duration=duration_min,
            min_temperature_celsius=min_temp,
            max_wind_force_bft=max_wind,
            max_precipitation=precip,
            remarks_field=remarks_field,
            requires_morning_visit=requires_morning,
            requires_evening_visit=requires_evening,
            requires_june_visit=requires_june,
            requires_maternity_period_visit=requires_maternity,
        )
        # assign derived attributes (persisted)
        visit.part_of_day = part_of_day
        visit.start_time = start_time
        setattr(visit, "start_time_text", start_time_text)
        # Set higher priority for tight windows (<= threshold)
        try:
            window_days = (v["to_date"] - v["from_date"]).days
            if window_days <= MIN_EFFECTIVE_WINDOW_DAYS:
                visit.priority = 1
        except Exception:
            pass
        next_nr += 1
        # attach relations
        # Attach existing entities by loading references to avoid transient instances
        visit.functions = list(
            (
                await db.execute(
                    select(Function).where(Function.id.in_(function_ids_set))
                )
            )
            .scalars()
            .all()
        )
        visit.species = list(
            (await db.execute(select(Species).where(Species.id.in_(species_ids_set))))
            .scalars()
            .all()
        )
        db.add(visit)
        created.append(visit)

    return created, warnings


async def duplicate_cluster_with_visits(
    db: AsyncSession,
    source_cluster: Cluster,
    new_number: int,
    new_address: str,
) -> Cluster:
    """Duplicate a cluster and copy all its visits with new sequencing.

    Each original group series gets a new group_id; visit_nr restarts at 1 for the new cluster.
    """

    new_cluster = Cluster(
        project_id=source_cluster.project_id,
        address=new_address,
        cluster_number=new_number,
    )
    db.add(new_cluster)
    await db.flush()

    visits = (
        (
            await db.execute(
                select(Visit)
                .where(Visit.cluster_id == source_cluster.id)
                .options(selectinload(Visit.functions), selectinload(Visit.species))
                .order_by(Visit.visit_nr)
            )
        )
        .scalars()
        .all()
    )
    # map old group_id -> new group_id
    group_map: dict[str | None, str | None] = {None: None}
    next_nr = 1
    for v in visits:
        if v.group_id not in group_map:
            group_map[v.group_id] = str(uuid4()) if v.group_id else None
        clone = Visit(
            cluster_id=new_cluster.id,
            group_id=group_map[v.group_id],
            required_researchers=v.required_researchers,
            visit_nr=next_nr,
            from_date=v.from_date,
            to_date=v.to_date,
            duration=v.duration,
            min_temperature_celsius=v.min_temperature_celsius,
            max_wind_force_bft=v.max_wind_force_bft,
            max_precipitation=v.max_precipitation,
            part_of_day=v.part_of_day,
            start_time=v.start_time,
            expertise_level=v.expertise_level,
            wbc=v.wbc,
            fiets=v.fiets,
            hup=v.hup,
            dvp=v.dvp,
            remarks_planning=v.remarks_planning,
            remarks_field=v.remarks_field,
            planned_week=v.planned_week,
            priority=v.priority,
            preferred_researcher_id=v.preferred_researcher_id,
            advertized=v.advertized,
            quote=v.quote,
        )
        next_nr += 1
        # copy relations (ids only)
        clone.functions = list(
            (
                await db.execute(
                    select(Function).where(Function.id.in_([f.id for f in v.functions]))
                )
            )
            .scalars()
            .all()
        )
        clone.species = list(
            (
                await db.execute(
                    select(Species).where(Species.id.in_([s.id for s in v.species]))
                )
            )
            .scalars()
            .all()
        )
        clone.researchers = []
        db.add(clone)

    return new_cluster

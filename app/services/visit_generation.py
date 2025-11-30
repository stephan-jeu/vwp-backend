from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import uuid4
import os
import logging

from sqlalchemy import Select, select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.species import Species
from app.models.visit import (
    Visit,
)


_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}
# Use uvicorn's error logger so messages always appear in console
_logger = logging.getLogger("uvicorn.error")

# Minimum acceptable effective window length (days) for a combined bucket
MIN_EFFECTIVE_WINDOW_DAYS = int(os.getenv("MIN_EFFECTIVE_WINDOW_DAYS", "14"))

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


def _is_exception_family_protocol(p: Protocol) -> bool:
    try:
        fam = getattr(getattr(p, "species", None), "family", None)
        name = _normalize_family_name(getattr(fam, "name", None))
        return name == "pad"
    except Exception:
        return False


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


def _is_smp(p: Protocol) -> bool:
    try:
        fn = getattr(p, "function", None)
        name = getattr(fn, "name", "") or ""
        return name.startswith("SMP")
    except Exception:
        return False


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

    a_smp = _is_smp(a)
    b_smp = _is_smp(b)

    # SMP gating: must both be SMP and same family; never allow cross-family exceptions
    if a_smp or b_smp:
        if not (a_smp and b_smp):
            return False
        return _same_family(a, b) or _same_family_name(a, b)

    # Legacy behavior for non-SMP
    if _same_family(a, b) or _same_family_name(a, b):
        return True
    return _is_allowed_cross_family(a, b)


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

    ref_start = protocol.start_timing_reference or ""
    ref_end = getattr(protocol, "end_timing_reference", None) or ""

    if ref_start == "DAYTIME":
        return {"Dag"}
    if ref_start == "ABSOLUTE_TIME":
        # Do not over-constrain: allow both, actual part is decided later by assignment/split
        return {"Avond", "Ochtend"}

    # Overnight window defined by separate start/end allows both
    if ref_start == "SUNSET" and ref_end == "SUNRISE":
        return {"Avond", "Ochtend"}
    if ref_start == "SUNSET":
        return {"Avond"}
    if ref_start == "SUNRISE":
        return {"Ochtend"}
    if ref_start == "SUNSET_TO_SUNRISE":
        return {"Avond", "Ochtend"}
    return None


# ---- Helpers: Allowed parts and coalescing ---------------------------------


def _compute_allowed_parts_for_entry(protocols: list[Protocol]) -> set[str] | None:
    """Intersect allowed part-of-day across protocols in a visit entry.

    Returns None if unconstrained; otherwise a non-empty set of allowed parts.
    """
    allowed: set[str] | None = None
    for p in protocols:
        opts = _derive_part_options(p)
        if allowed is None:
            allowed = opts
        else:
            if opts is None:
                continue
            allowed = allowed & opts if allowed is not None else opts
    return allowed


def _coalesce_visits(entries: list[dict]) -> list[dict]:
    """Merge entries with identical (from, to, chosen_part_of_day) when compatible.

    If combining protocol sets would violate compatibility, keep separate bins
    for the same key.
    """
    bins_by_key: dict[tuple[date, date, str | None], list[dict]] = {}
    for v in entries:
        key = (v["from_date"], v["to_date"], v.get("chosen_part_of_day"))
        bins = bins_by_key.setdefault(key, [])
        placed = False
        for b in bins:
            # Check if protocols in v are compatible with all protocols already in bin
            if all(
                _allow_together(p, q) for p in v["protocols"] for q in b["protocols"]
            ):
                # Merge unique protocols
                existing_ids = {p.id for p in b["protocols"]}
                for p in v["protocols"]:
                    if p.id not in existing_ids:
                        b["protocols"].append(p)
                        existing_ids.add(p.id)
                # Merge proto_parts if present, keeping stricter constraints (intersection)
                if "proto_parts" in v or "proto_parts" in b:
                    b.setdefault("proto_parts", {})
                    _merge_proto_parts(b["proto_parts"], v.get("proto_parts", {}) or {})
                # Merge proto_pvw_ids
                if "proto_pvw_ids" in v or "proto_pvw_ids" in b:
                    b.setdefault("proto_pvw_ids", {})
                    b["proto_pvw_ids"].update(v.get("proto_pvw_ids", {}) or {})
                placed = True
                break
        if not placed:
            bins.append(
                {
                    "from_date": v["from_date"],
                    "to_date": v["to_date"],
                    "chosen_part_of_day": v.get("chosen_part_of_day"),
                    "protocols": list(v["protocols"]),
                    "proto_parts": (v.get("proto_parts") or {}),
                    "proto_pvw_ids": (v.get("proto_pvw_ids") or {}),
                }
            )
    # Flatten bins preserving stable order by from_date
    result: list[dict] = []
    for _key, group in bins_by_key.items():
        result.extend(group)
    return result


@dataclass
class _BucketEntry:
    """Lightweight structure for an intermediate visit bucket.

    This mirrors the dict structure used throughout the pipeline and offers
    helpers to convert back and forth to avoid a large refactor.
    """

    from_date: date
    to_date: date
    protocols: list[Protocol]
    chosen_part_of_day: str | None = None
    proto_parts: dict[int, set[str] | None] | None = None
    proto_pvw_ids: dict[int, int] | None = None

    @staticmethod
    def from_dict(d: dict) -> "_BucketEntry":
        return _BucketEntry(
            from_date=d["from_date"],
            to_date=d["to_date"],
            protocols=list(d.get("protocols", [])),
            chosen_part_of_day=d.get("chosen_part_of_day"),
            proto_parts=(d.get("proto_parts") or {}),
            proto_pvw_ids=(d.get("proto_pvw_ids") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "protocols": self.protocols,
            "chosen_part_of_day": self.chosen_part_of_day,
            "proto_parts": (self.proto_parts or {}),
            "proto_pvw_ids": (self.proto_pvw_ids or {}),
        }


def _merge_proto_parts(
    into: dict[int, set[str] | None], incoming: dict[int, set[str] | None]
) -> None:
    """Merge incoming proto_parts into into using intersection for stricter constraints."""
    for pid, parts in incoming.items():
        cur = into.get(pid)
        if cur is None:
            into[pid] = parts
        elif parts is None:
            continue
        else:
            into[pid] = (
                (cur & parts)
                if (cur is not None and parts is not None)
                else (cur or parts)
            )


def _respects_min_gap(planned: list[date], v_from: date, days: int | None) -> bool:
    """Return True if v_from is allowed under min-gap rules against planned dates."""
    if not days:
        return True
    last_before = max([d for d in planned if d <= v_from], default=None)
    if last_before is None:
        return True
    return not (v_from < last_before + timedelta(days=days))


def _relax_single_protocol_visit_starts(
    visits_to_create: list[dict],
    proto_windows: dict[int, list[tuple[int, date, date, set[str] | None, int]]],
    proto_id_to_protocol: dict[int, Protocol],
) -> None:
    """Relax start dates for single-protocol visits when buckets are too restrictive.

    For each protocol, walk its realised visits in chronological order and, for
    entries that contain only that protocol, try to move the visit ``from_date``
    earlier, bounded by:

    * The protocol visit window ``window_from`` that contains the current
      ``from_date``.
    * The protocol's own ``min_period_between_visits`` to the previous realised
      visit of the same protocol.

    Only leftward moves are allowed and we never cross the visit's current
    ``to_date``. Multi-protocol visits are left untouched.

    Args:
        visits_to_create: Mutable list of visit dicts produced by bucketing and
            completion.
        proto_windows: Mapping of protocol id to its visit windows in the
            current year.
        proto_id_to_protocol: Mapping of protocol id to Protocol instances.
    """

    if not visits_to_create or not proto_windows:
        return

    for pid, protocol in proto_id_to_protocol.items():
        windows = proto_windows.get(pid)
        if not windows:
            continue

        # Collect realised visits that contain this protocol.
        entries = [
            e for e in visits_to_create if any(pp.id == pid for pp in e["protocols"])
        ]
        if not entries:
            continue

        entries.sort(key=lambda e: e["from_date"])

        # Precompute simple (wf, wt) pairs for membership checks.
        window_pairs: list[tuple[date, date]] = [
            (wf, wt) for _vidx, wf, wt, _parts, _pvw_id in windows
        ]

        gap_days = _unit_to_days(
            getattr(protocol, "min_period_between_visits_value", None),
            getattr(protocol, "min_period_between_visits_unit", None),
        )

        previous_from: date | None = None
        for entry in entries:
            v_from: date = entry["from_date"]
            v_to: date = entry["to_date"]

            # Find protocol windows that actually contain this realised start.
            containing_wfs = [wf for (wf, wt) in window_pairs if wf <= v_from <= wt]
            if not containing_wfs:
                previous_from = v_from
                continue

            window_from = min(containing_wfs)
            earliest_allowed = window_from
            if previous_from is not None and gap_days:
                from_with_gap = previous_from + timedelta(days=gap_days)
                if from_with_gap > earliest_allowed:
                    earliest_allowed = from_with_gap

            # Only relax single-protocol visits and only move earlier, never later.
            if (
                len(entry.get("protocols", [])) == 1
                and earliest_allowed < v_from
                and earliest_allowed <= v_to
            ):
                if _DEBUG_VISIT_GEN:
                    _logger.info(
                        "relax single-proto visit proto=%s %s->%s -> %s->%s",
                        pid,
                        v_from.isoformat(),
                        v_to.isoformat(),
                        earliest_allowed.isoformat(),
                        v_to.isoformat(),
                    )
                entry["from_date"] = earliest_allowed
                v_from = earliest_allowed

            previous_from = v_from


def _entry_contains_protocol(entry: dict, p: Protocol) -> bool:
    return any(pp.id == p.id for pp in entry["protocols"])


def _overlap_days(v_from: date, v_to: date, wf: date, wt: date) -> int:
    overlap_from = max(v_from, wf)
    overlap_to = min(v_to, wt)
    return (overlap_to - overlap_from).days


def _part_allowed(chosen_part: str | None, parts: set[str] | None) -> bool:
    return parts is None or chosen_part is None or chosen_part in parts


def _add_protocol_to_entry(
    entry: dict, p: Protocol, parts: set[str] | None, planned: list[date]
) -> None:
    entry["protocols"].append(p)
    entry.setdefault("proto_parts", {})[p.id] = parts
    planned.append(entry["from_date"])
    planned.sort()


def _complete_missing_occurrences(
    visits_to_create: list[dict],
    proto_windows: dict[int, list[tuple[int, date, date, set[str] | None]]],
    proto_id_to_protocol: dict[int, Protocol],
) -> None:
    """Ensure each protocol has required number of planned occurrences.

    Mutates visits_to_create in place by either attaching to compatible entries or
    creating new dedicated entries while respecting overlap, part-of-day, compatibility,
    and per-protocol minimum gaps.
    """
    proto_to_planned_froms: dict[int, list[date]] = defaultdict(list)
    for entry in visits_to_create:
        for p in entry["protocols"]:
            proto_to_planned_froms[p.id].append(entry["from_date"])

    for pid, windows in proto_windows.items():
        p = proto_id_to_protocol[pid]
        # Group windows by (wf,wt)
        group_counts: dict[tuple[date, date], dict] = {}
        for _vidx, wf, wt, parts, _pvw_id in windows:
            key = (wf, wt)
            g = group_counts.get(key)
            if g is None:
                group_counts[key] = {"count": 1, "parts": parts}
            else:
                g["count"] += 1
                if g["parts"] is None:
                    g["parts"] = parts
                elif parts is not None:
                    g["parts"] = set(g["parts"]) & set(parts)

        planned = sorted(proto_to_planned_froms.get(pid, []))
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "completion grouped proto=%s groups=%s planned=%s",
                getattr(p, "id", None),
                [
                    (
                        wf.isoformat(),
                        wt.isoformat(),
                        grp["count"],
                        list(grp["parts"]) if grp["parts"] else None,
                    )
                    for (wf, wt), grp in sorted(group_counts.items())
                ],
                [d.isoformat() for d in planned],
            )
        proto_days = _unit_to_days(
            p.min_period_between_visits_value, p.min_period_between_visits_unit
        )
        for (wf, wt), grp in sorted(group_counts.items()):
            required = grp["count"]
            parts = grp["parts"]
            have = sum(1 for d in planned if wf <= d <= wt)
            missing = max(0, required - have)
            for _ in range(missing):
                attached = False
                for entry in visits_to_create:
                    v_from = entry["from_date"]
                    v_to = entry["to_date"]
                    if v_from in planned:
                        continue
                    if _overlap_days(v_from, v_to, wf, wt) < MIN_EFFECTIVE_WINDOW_DAYS:
                        continue
                    if not _part_allowed(entry.get("chosen_part_of_day"), parts):
                        continue
                    if not all(_allow_together(p, q) for q in entry["protocols"]):
                        continue
                    if not _respects_min_gap(planned, v_from, proto_days):
                        continue
                    if _entry_contains_protocol(entry, p):
                        continue
                    _add_protocol_to_entry(entry, p, parts, planned)
                    attached = True
                    if _DEBUG_VISIT_GEN:
                        _logger.info(
                            "completion attach proto=%s to existing visit %s->%s part=%s",
                            getattr(p, "id", None),
                            v_from.isoformat(),
                            v_to.isoformat(),
                            entry.get("chosen_part_of_day"),
                        )
                    break
                if attached:
                    continue
                # Create new dedicated visit within [wf,wt]
                last_planned = max([d for d in planned if d <= wt], default=None)
                candidate_from = wf
                if last_planned is not None and proto_days:
                    candidate_from = max(
                        candidate_from, last_planned + timedelta(days=proto_days)
                    )
                if candidate_from > wt:
                    # Fallback: try placing *before* the earliest planned occurrence
                    # within this window, still respecting min-gap and bounds. This
                    # handles wide windows where the first planned visit ended up
                    # late (e.g. in a tight combined bucket), leaving only room on
                    # the left side of the window for additional occurrences.
                    earliest_in_window = min(
                        [d for d in planned if wf <= d <= wt], default=None
                    )
                    fallback_from: date | None = None
                    # Prefer using the full left side of the window when possible.
                    # We only require that there is at least one planned visit
                    # inside [wf, wt] to justify this fallback; min-gap to earlier
                    # visits is still enforced via _respects_min_gap.
                    if earliest_in_window is not None:
                        fallback_from = wf

                    if (
                        fallback_from is None
                        or fallback_from > wt
                        or not _respects_min_gap(planned, fallback_from, proto_days)
                    ):
                        if _DEBUG_VISIT_GEN:
                            _logger.warning(
                                "completion cannot place proto=%s within window %s->%s (min-gap or bounds)",
                                getattr(p, "id", None),
                                wf.isoformat(),
                                wt.isoformat(),
                            )
                        continue

                    candidate_from = fallback_from
                candidate_to = wt
                nxt_candidates = [d for d in planned if d >= candidate_from]
                nxt = min(nxt_candidates) if nxt_candidates else None
                if nxt is not None:
                    before_next = nxt - timedelta(days=1)
                    if before_next >= candidate_from:
                        candidate_to = min(candidate_to, before_next)
                chosen_part = None
                if parts and len(parts) > 0:
                    if "Ochtend" in parts:
                        chosen_part = "Ochtend"
                    elif "Avond" in parts:
                        chosen_part = "Avond"
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
                planned.append(candidate_from)
                planned.sort()
                if _DEBUG_VISIT_GEN:
                    _logger.info(
                        "completion create visit proto=%s (%s,%s) part=%s",
                        getattr(p, "id", None),
                        candidate_from.isoformat(),
                        candidate_to.isoformat(),
                        chosen_part,
                    )


def _derive_start_time_minutes(protocol: Protocol) -> int | None:
    """Compute start time in minutes relative to the timing reference.

    Returns the stored ``start_time_relative_minutes`` value as-is, for all
    timing references. Semantics of that value (e.g. minutes before/after
    sunrise or sunset) are handled by the text-formatting layer.
    """

    rel = protocol.start_time_relative_minutes
    if rel is None:
        return None
    return rel


def _derive_end_time_minutes(protocol: Protocol) -> int | None:
    """Return end time in minutes relative to the end timing reference, if set."""
    rel = getattr(protocol, "end_time_relative_minutes", None)
    if rel is None:
        return None
    # Interpret stored relative minutes as "subtract from reference" semantics:
    # a positive stored value means the end is before the reference, and a negative
    # stored value means after the reference. Effective minutes are thus -rel.
    return -int(rel)


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
    *,
    protocols: list[Protocol] | None = None,
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
            "visit_gen start cluster=%s functions=%s species=%s protocols=%s",
            getattr(cluster, "id", None),
            function_ids,
            species_ids,
            [getattr(p, "id", None) for p in (protocols or [])] or None,
        )

    warnings: list[str] = []

    # When protocols are provided, skip the legacy ids guard
    if protocols is None and (not function_ids or not species_ids):
        return [], warnings

    # Resolve protocols if not provided
    if protocols is None:
        # Fetch all protocols for selected pairs and their windows (eager-load windows)
        stmt: Select[tuple[Protocol]] = (
            select(Protocol)
            .where(
                Protocol.function_id.in_(function_ids),
                Protocol.species_id.in_(species_ids),
            )
            .options(
                selectinload(Protocol.visit_windows),
                selectinload(Protocol.species).selectinload(Species.family),
                selectinload(Protocol.function),
            )
        )
        protocols = (await db.execute(stmt)).scalars().unique().all()

    if not protocols:
        return [], warnings

    # Windows loaded via selectinload

    # continue with bucketing logic

    # 1) Precompute shifted windows per protocol and tightness key
    #    Shift only the start per visit_index using the protocol's own min period;
    #    keep window_to fixed in the current year.
    proto_id_to_protocol: dict[int, Protocol] = {p.id: p for p in protocols}
    # (vidx, wf, wt, parts, pvw_id)
    proto_windows: dict[int, list[tuple[int, date, date, set[str] | None, int]]] = {}
    for p in protocols:
        items: list[tuple[int, date, date, set[str] | None, int]] = []
        if p.visit_windows:
            for w in sorted(p.visit_windows, key=lambda w: w.visit_index):
                vidx = w.visit_index
                # Do not shift window start by min-gap here; rely on explicit windows.
                wf = _to_current_year(w.window_from)
                wt = _to_current_year(w.window_to)
                if wf <= wt:
                    natural_parts = _derive_part_options(p)
                    parts = natural_parts
                    # Force required morning/evening on first visit index by constraining allowed parts
                    if vidx == 1:
                        forced: set[str] | None = None
                        if getattr(p, "requires_morning_visit", False):
                            forced = {"Ochtend"}
                        elif getattr(p, "requires_evening_visit", False):
                            forced = {"Avond"}
                        if forced is not None:
                            if natural_parts is None:
                                parts = forced
                            else:
                                inter = natural_parts & forced
                                if len(inter) == 0:
                                    if _DEBUG_VISIT_GEN:
                                        _logger.warning(
                                            "proto %s first-visit forced part incompatible with natural parts; forced=%s natural=%s",
                                            getattr(p, "id", None),
                                            list(forced),
                                            list(natural_parts),
                                        )
                                    # Keep natural parts to avoid collapsing windows; requirement may not be met
                                    parts = natural_parts
                                else:
                                    parts = inter
                    items.append((vidx, wf, wt, parts, w.id))
        if items:
            proto_windows[p.id] = items
            if _DEBUG_VISIT_GEN:
                _logger.info(
                    "proto %s windows: %s",
                    getattr(p, "id", None),
                    [
                        (
                            vidx,
                            wf.isoformat(),
                            wt.isoformat(),
                            list(parts) if parts else None,
                            pvw_id,
                        )
                        for (vidx, wf, wt, parts, pvw_id) in items
                    ],
                )

    # Map pvw_id -> visit_index for remarks generation
    pvw_id_to_vidx: dict[int, int] = {}
    for items in proto_windows.values():
        for vidx, _, _, _, pvw_id in items:
            pvw_id_to_vidx[pvw_id] = vidx

    def tightness_key(p: Protocol) -> tuple[int, date]:
        items = proto_windows.get(p.id, [])
        if not items:
            return (10_000, date.max)
        max_idx_item = max(items, key=lambda it: it[0])
        _, wf, wt, _, _ = max_idx_item
        length = (wt - wf).days
        earliest = min(it[1] for it in items)
        return (length, earliest)

    ordered = sorted(
        [
            p
            for p in protocols
            if p.id in proto_windows and not _is_exception_family_protocol(p)
        ],
        key=tightness_key,
    )
    if _DEBUG_VISIT_GEN:
        _logger.info(
            "proto options: %s",
            [
                (
                    getattr(p, "id", None),
                    getattr(p, "requires_morning_visit", False),
                    getattr(p, "requires_evening_visit", False),
                    getattr(p, "start_timing_reference", None),
                    getattr(p, "end_timing_reference", None),
                    list(_derive_part_options(p) or []),
                )
                for p in ordered
            ],
        )

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
            first_parts: set[str] | None,
            first_pvw_id: int,
        ):
            self.from_date = wf
            self.to_date = wt
            self.parts = parts
            self.proto_ids: set[int] = {first_proto.id}
            self.last_from_by_proto: dict[int, date] = {first_proto.id: wf}
            # carry per-protocol allowed parts as derived for the window placed in this bucket
            self.proto_parts: dict[int, set[str] | None] = {first_proto.id: first_parts}
            self.proto_pvw_ids: dict[int, int] = {first_proto.id: first_pvw_id}

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
            # Ignore parts-of-day intersection in Phase 1; decide parts in a later split phase
            return (True, (new_from, new_to), self.parts)

        def place(
            self,
            p: Protocol,
            wf: date,
            wt: date,
            parts: set[str] | None,
            new_from: date,
            new_to: date,
            new_parts: set[str] | None,
            pvw_id: int,
        ):
            self.from_date = new_from
            self.to_date = new_to
            # Keep parts unchanged in Phase 1; splitting decides later
            self.parts = self.parts
            self.proto_ids.add(p.id)
            self.last_from_by_proto[p.id] = new_from
            self.proto_parts[p.id] = parts
            self.proto_pvw_ids[p.id] = pvw_id

    buckets: list[_Bucket] = []
    if ordered:
        first = ordered[0]
        # Deduplicate initial buckets by (from,to,parts_signature)
        seen_keys: set[tuple[date, date, tuple[str, ...] | None]] = set()
        first_proto_days = _unit_to_days(
            first.min_period_between_visits_value, first.min_period_between_visits_unit
        )
        last_from_first: date | None = None
        prev_wf_first: date | None = None
        for vidx, wf, wt, parts, pvw_id in proto_windows[first.id]:
            parts_key: tuple[str, ...] | None = (
                tuple(sorted(parts)) if parts is not None else None
            )
            key = (wf, wt, parts_key)
            if key in seen_keys:
                if _DEBUG_VISIT_GEN:
                    _logger.info(
                        "skip duplicate seed bucket for first proto: wf=%s wt=%s parts=%s",
                        wf.isoformat(),
                        wt.isoformat(),
                        list(parts) if parts else None,
                    )
                continue
            seen_keys.add(key)

            adj_wf = wf
            if vidx > 1 and last_from_first is not None and first_proto_days:
                window_gap_days = (
                    (wf - prev_wf_first).days if prev_wf_first is not None else None
                )
                required_from_gap = last_from_first + timedelta(days=first_proto_days)
                if window_gap_days is not None and window_gap_days >= first_proto_days:
                    required_from = wf
                else:
                    required_from = required_from_gap
                adj_wf = max(wf, required_from)

            if adj_wf <= wt:
                # Seed without parts for Phase 1
                buckets.append(_Bucket(adj_wf, wt, None, first, vidx, parts, pvw_id))
                last_from_first = adj_wf
                prev_wf_first = wf

    for p in ordered[1:]:
        last_from_p: date | None = None
        for vidx, wf, wt, parts, pvw_id in proto_windows[p.id]:
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
                    b.place(p, wf, wt, parts, nf, nt, nparts, pvw_id)
                    last_from_p = nf
                    if _DEBUG_VISIT_GEN:
                        _logger.info(
                            "place proto=%s vidx=%s into existing bucket: new_from=%s new_to=%s parts=%s",
                            getattr(p, "id", None),
                            vidx,
                            nf.isoformat(),
                            nt.isoformat(),
                            list(nparts) if nparts else None,
                        )
                    placed = True
                    break
            if not placed:
                # Opening a new bucket: respect window spacing vs min-gap
                adj_wf = wf
                if vidx > 1 and last_from_p is not None:
                    # Look up previous window_from for this protocol (vidx-1)
                    prev_wf = None
                    for v_i, wf_i, _wt_i, _pa_i, _ in proto_windows.get(p.id, []):
                        if v_i == vidx - 1:
                            prev_wf = wf_i
                            break
                    window_gap_days = (
                        (wf - prev_wf).days if prev_wf is not None else None
                    )
                    required_from_gap = (
                        last_from_p + timedelta(days=(proto_days or 0))
                        if proto_days
                        else last_from_p
                    )
                    if (
                        window_gap_days is not None
                        and proto_days
                        and window_gap_days >= proto_days
                    ):
                        # Windows already encode a gap >= min-gap; do not push start by min-gap
                        required_from = wf
                    else:
                        required_from = required_from_gap
                    adj_wf = max(wf, required_from)
                    if _DEBUG_VISIT_GEN:
                        _logger.info(
                            "open new bucket: proto=%s vidx=%s wf=%s prev_wf=%s window_gap=%s min_gap=%s last_from=%s required_from=%s adj_wf=%s",
                            getattr(p, "id", None),
                            vidx,
                            wf.isoformat(),
                            prev_wf.isoformat() if prev_wf else None,
                            window_gap_days,
                            proto_days,
                            last_from_p.isoformat() if last_from_p else None,
                            (
                                required_from.isoformat()
                                if isinstance(required_from, date)
                                else required_from
                            ),
                            adj_wf.isoformat(),
                        )
                if adj_wf <= wt:
                    # Create without parts for Phase 1
                    b = _Bucket(adj_wf, wt, None, p, vidx, parts, pvw_id)
                    buckets.append(b)
                    last_from_p = adj_wf
                    if _DEBUG_VISIT_GEN:
                        _logger.info(
                            "new bucket proto=%s vidx=%s wf=%s wt=%s required_from=%s adj_wf=%s",
                            getattr(p, "id", None),
                            vidx,
                            wf.isoformat(),
                            wt.isoformat(),
                            (
                                (
                                    last_from_p - timedelta(days=(proto_days or 0))
                                ).isoformat()
                                if last_from_p and proto_days
                                else None
                            ),
                            adj_wf.isoformat(),
                        )

    # Emit visits from buckets
    # Each bucket becomes one visit with the bucket window and preferred part-of-day.
    visits_to_create: list[dict] = []
    for b in buckets:
        chosen_part = None
        # Phase 1: chosen_part is intentionally left None; decided in split phase
        visits_to_create.append(
            {
                "from_date": b.from_date,
                "to_date": b.to_date,
                "protocols": [proto_id_to_protocol[pid] for pid in sorted(b.proto_ids)],
                "chosen_part_of_day": chosen_part,
                "proto_parts": {pid: b.proto_parts.get(pid) for pid in b.proto_ids},
                "proto_pvw_ids": {pid: b.proto_pvw_ids.get(pid) for pid in b.proto_ids},
            }
        )
    if _DEBUG_VISIT_GEN and visits_to_create:
        _logger.info(
            "pre-coalesce visits: %s",
            [
                (
                    v["from_date"].isoformat(),
                    v["to_date"].isoformat(),
                    v.get("chosen_part_of_day"),
                    [getattr(p, "id", None) for p in v["protocols"]],
                )
                for v in visits_to_create
            ],
        )

    # Coalesce duplicate windows (same from/to and part) by unioning protocols
    if visits_to_create:
        visits_to_create = _coalesce_visits(visits_to_create)
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "post-coalesce visits: %s",
                [
                    (
                        v["from_date"].isoformat(),
                        v["to_date"].isoformat(),
                        v.get("chosen_part_of_day"),
                        [getattr(p, "id", None) for p in v["protocols"]],
                    )
                    for v in visits_to_create
                ],
            )

    # Phase 2: split buckets by incompatible parts-of-day and assign chosen_part
    def _split_buckets_by_parts(entries: list[dict]) -> list[dict]:
        result: list[dict] = []
        for e in entries:
            protos: list[Protocol] = e.get("protocols", [])
            per_proto_parts: dict[int, set[str] | None] = e.get("proto_parts", {}) or {}
            per_proto_pvw_ids: dict[int, int] = e.get("proto_pvw_ids", {}) or {}
            allows: list[set[str]] = []
            for p in protos:
                pp = per_proto_parts.get(p.id)
                allows.append(pp or (_derive_part_options(p) or set()))
            if _DEBUG_VISIT_GEN:
                _logger.info(
                    "split parts per entry %s->%s: %s",
                    e["from_date"].isoformat(),
                    e["to_date"].isoformat(),
                    [
                        (
                            getattr(p, "id", None),
                            sorted(list(allows[idx])) if allows[idx] else None,
                        )
                        for idx, p in enumerate(protos)
                    ],
                )

            # Classify by allowed parts in this bucket
            morning_only: list[Protocol] = []
            evening_only: list[Protocol] = []
            day_only: list[Protocol] = []
            flex: list[Protocol] = []
            for p, s in zip(protos, allows):
                has_m = "Ochtend" in s
                has_e = "Avond" in s
                has_d = "Dag" in s
                cnt = int(has_m) + int(has_e) + int(has_d)
                if cnt >= 2:
                    flex.append(p)
                elif has_m:
                    morning_only.append(p)
                elif has_e:
                    evening_only.append(p)
                elif has_d:
                    day_only.append(p)
                else:
                    flex.append(p)

            # Special case: only flex present -> default to a single Morning bucket
            if not morning_only and not evening_only and not day_only and flex:
                result.append(
                    {
                        "from_date": e["from_date"],
                        "to_date": e["to_date"],
                        "protocols": flex,
                        "chosen_part_of_day": "Ochtend",
                        "proto_parts": {p.id: per_proto_parts.get(p.id) for p in flex},
                        "proto_pvw_ids": {
                            p.id: per_proto_pvw_ids.get(p.id) for p in flex
                        },
                    }
                )
                continue

            morning_assigned_ids: set[int] = set()
            # Morning bucket: only if strictly required by morning-only protocols
            if morning_only:
                assigned = set(id(p) for p in morning_only)
                morning_protos = morning_only + [
                    p for p in flex if id(p) not in assigned
                ]
                if morning_protos:
                    result.append(
                        {
                            "from_date": e["from_date"],
                            "to_date": e["to_date"],
                            "protocols": morning_protos,
                            "chosen_part_of_day": "Ochtend",
                            "proto_parts": {
                                p.id: per_proto_parts.get(p.id) for p in morning_protos
                            },
                            "proto_pvw_ids": {
                                p.id: per_proto_pvw_ids.get(p.id)
                                for p in morning_protos
                            },
                        }
                    )
                    morning_assigned_ids = {p.id for p in morning_protos}
                # remove flex assigned to morning
                flex = [p for p in flex if p not in morning_protos]

            # Evening bucket gets evening-only plus remaining flex (exclude anything assigned to morning)
            if evening_only or flex:
                evening_protos = evening_only + [
                    p for p in flex if p.id not in morning_assigned_ids
                ]
                if evening_protos:
                    result.append(
                        {
                            "from_date": e["from_date"],
                            "to_date": e["to_date"],
                            "protocols": evening_protos,
                            "chosen_part_of_day": "Avond",
                            "proto_parts": {
                                p.id: per_proto_parts.get(p.id) for p in evening_protos
                            },
                            "proto_pvw_ids": {
                                p.id: per_proto_pvw_ids.get(p.id)
                                for p in evening_protos
                            },
                        }
                    )

            # Only daytime and no morning/evening present
            if day_only and not morning_only and not evening_only:
                result.append(
                    {
                        "from_date": e["from_date"],
                        "to_date": e["to_date"],
                        "protocols": day_only,
                        "chosen_part_of_day": "Dag",
                        "proto_parts": {
                            p.id: per_proto_parts.get(p.id) for p in day_only
                        },
                        "proto_pvw_ids": {
                            p.id: per_proto_pvw_ids.get(p.id) for p in day_only
                        },
                    }
                )

            # If nothing classified, keep original
            if not morning_only and not evening_only and not day_only and not flex:
                result.append(e)
        return result

    if visits_to_create:
        # Decide parts-of-day by splitting incompatible sets
        visits_to_create = _split_buckets_by_parts(visits_to_create)
        # Re-coalesce as multiple buckets may now share same keys
        visits_to_create = _coalesce_visits(visits_to_create)
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "post-part-split visits: %s",
                [
                    (
                        v["from_date"].isoformat(),
                        v["to_date"].isoformat(),
                        v.get("chosen_part_of_day"),
                        [getattr(p, "id", None) for p in v["protocols"]],
                    )
                    for v in visits_to_create
                ],
            )

    # Completion pass: ensure each protocol has one planned visit per visit_index window
    # Match planned occurrences to windows by pvw_id.
    satisfied_pvw_ids: dict[int, set[int]] = defaultdict(set)
    proto_to_planned_froms: dict[int, list[date]] = defaultdict(list)
    for entry in visits_to_create:
        for p in entry["protocols"]:
            proto_to_planned_froms[p.id].append(entry["from_date"])
            if "proto_pvw_ids" in entry and p.id in entry["proto_pvw_ids"]:
                satisfied_pvw_ids[p.id].add(entry["proto_pvw_ids"][p.id])

    for pid, windows in proto_windows.items():
        p = proto_id_to_protocol[pid]
        # Pad-family protocols are handled in a simple one-visit-per-window mode
        # after the main completion logic; skip them here.
        if _is_exception_family_protocol(p):
            continue
        planned = sorted(proto_to_planned_froms.get(pid, []))
        proto_days = _unit_to_days(
            p.min_period_between_visits_value, p.min_period_between_visits_unit
        )

        # Iterate windows in order. If pvw_id not satisfied, plan it.
        for vidx, wf, wt, parts, pvw_id in sorted(windows, key=lambda w: w[0]):
            if pvw_id in satisfied_pvw_ids[pid]:
                continue

            # Try to attach to an existing visit
            attached = False
            for entry in visits_to_create:
                v_from = entry["from_date"]
                v_to = entry["to_date"]
                overlap_from = max(v_from, wf)
                overlap_to = min(v_to, wt)
                overlap_days = (overlap_to - overlap_from).days
                chosen_part = entry.get("chosen_part_of_day")
                part_ok = parts is None or chosen_part is None or chosen_part in parts
                compatible = all(_allow_together(p, q) for q in entry["protocols"])

                # Do not attach if protocol already present
                if _entry_contains_protocol(entry, p):
                    continue

                # Enforce per-protocol minimum gap against already planned dates
                min_gap_ok = True
                if proto_days:
                    last_before = max([d for d in planned if d <= v_from], default=None)
                    if last_before is not None and v_from < last_before + timedelta(
                        days=proto_days
                    ):
                        min_gap_ok = False

                if (
                    overlap_days >= MIN_EFFECTIVE_WINDOW_DAYS
                    and part_ok
                    and compatible
                    and min_gap_ok
                ):
                    entry["protocols"].append(p)
                    entry.setdefault("proto_parts", {})[p.id] = parts
                    entry.setdefault("proto_pvw_ids", {})[p.id] = pvw_id
                    planned.append(entry["from_date"])
                    planned.sort()
                    satisfied_pvw_ids[pid].add(pvw_id)
                    attached = True
                    if _DEBUG_VISIT_GEN:
                        _logger.info(
                            "completion attach proto=%s vidx=%s to existing visit %s->%s part=%s",
                            getattr(p, "id", None),
                            vidx,
                            v_from.isoformat(),
                            v_to.isoformat(),
                            chosen_part,
                        )
                    break

            if attached:
                continue

            # Create new dedicated visit within [wf,wt]
            last_planned = max([d for d in planned if d <= wt], default=None)
            candidate_from = wf
            if last_planned is not None and proto_days:
                candidate_from = max(
                    candidate_from, last_planned + timedelta(days=proto_days)
                )
            if candidate_from > wt:
                # Fallback: try placing *before* the earliest planned occurrence
                # within this window, still respecting min-gap and bounds. This
                # handles wide windows where the first planned visit ended up
                # late (e.g. in a tight combined bucket), leaving only room on
                # the left side of the window for additional occurrences.
                earliest_in_window = min(
                    [d for d in planned if wf <= d <= wt], default=None
                )
                fallback_from: date | None = None
                # Prefer using the full left side of the window when possible.
                # We only require that there is at least one planned visit
                # inside [wf, wt] to justify this fallback; min-gap to earlier
                # visits is still enforced via _respects_min_gap.
                if earliest_in_window is not None:
                    fallback_from = wf

                if (
                    fallback_from is None
                    or fallback_from > wt
                    or not _respects_min_gap(planned, fallback_from, proto_days)
                ):
                    if _DEBUG_VISIT_GEN:
                        _logger.warning(
                            "completion cannot place proto=%s vidx=%s within window %s->%s (min-gap or bounds)",
                            getattr(p, "id", None),
                            vidx,
                            wf.isoformat(),
                            wt.isoformat(),
                        )
                    continue

                candidate_from = fallback_from
            candidate_to = wt
            nxt_candidates = [d for d in planned if d >= candidate_from]
            nxt = min(nxt_candidates) if nxt_candidates else None
            if nxt is not None:
                before_next = nxt - timedelta(days=1)
                if before_next >= candidate_from:
                    candidate_to = min(candidate_to, before_next)
            chosen_part = None
            if parts and len(parts) > 0:
                if "Ochtend" in parts:
                    chosen_part = "Ochtend"
                elif "Avond" in parts:
                    chosen_part = "Avond"
                elif "Dag" in parts:
                    chosen_part = "Dag"

            visits_to_create.append(
                {
                    "from_date": candidate_from,
                    "to_date": candidate_to,
                    "protocols": [p],
                    "chosen_part_of_day": chosen_part,
                    "proto_parts": {p.id: parts},
                    "proto_pvw_ids": {p.id: pvw_id},
                }
            )
            planned.append(candidate_from)
            planned.sort()
            satisfied_pvw_ids[pid].add(pvw_id)
            if _DEBUG_VISIT_GEN:
                _logger.info(
                    "completion create visit proto=%s vidx=%s (%s,%s) part=%s",
                    getattr(p, "id", None),
                    vidx,
                    candidate_from.isoformat(),
                    candidate_to.isoformat(),
                    chosen_part,
                )

    # Re-coalesce duplicates after additions
    if _DEBUG_VISIT_GEN and visits_to_create:
        _logger.info(
            "pre-final-coalesce visits: %s",
            [
                (
                    v["from_date"].isoformat(),
                    v["to_date"].isoformat(),
                    v.get("chosen_part_of_day"),
                    [getattr(p, "id", None) for p in v["protocols"]],
                )
                for v in visits_to_create
            ],
        )
    if visits_to_create:
        visits_to_create = _coalesce_visits(visits_to_create)
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "final visits: %s",
                [
                    (
                        v["from_date"].isoformat(),
                        v["to_date"].isoformat(),
                        v.get("chosen_part_of_day"),
                        [getattr(p, "id", None) for p in v["protocols"]],
                    )
                    for v in visits_to_create
                ],
            )

    # First attempt: at-least-one part-of-day assignment per protocol BEFORE splitting
    def _assign_at_least_one(visits: list[dict]) -> None:
        allowed_parts_by_entry: dict[int, set[str] | None] = {
            idx: _compute_allowed_parts_for_entry(e["protocols"])
            for idx, e in enumerate(visits)
        }

        def set_part_if_allowed(entry_idx: int, part: str) -> bool:
            allowed = allowed_parts_by_entry.get(entry_idx)
            if allowed is None or part in allowed:
                visits[entry_idx]["chosen_part_of_day"] = part
                return True
            return False

        for p in protocols:
            entry_indexes = [
                i
                for i, e in enumerate(visits)
                if any(pp.id == p.id for pp in e["protocols"])
            ]
            if not entry_indexes:
                continue
            if getattr(p, "requires_morning_visit", False):
                if not any(
                    visits[i].get("chosen_part_of_day") == "Ochtend"
                    for i in entry_indexes
                ):
                    for i in entry_indexes:
                        if set_part_if_allowed(i, "Ochtend"):
                            if _DEBUG_VISIT_GEN:
                                _logger.info(
                                    "assign (pre-split) morning for proto=%s on %s->%s",
                                    getattr(p, "id", None),
                                    visits[i]["from_date"].isoformat(),
                                    visits[i]["to_date"].isoformat(),
                                )
                            break
            if getattr(p, "requires_evening_visit", False):
                if not any(
                    visits[i].get("chosen_part_of_day") == "Avond"
                    for i in entry_indexes
                ):
                    for i in entry_indexes:
                        if set_part_if_allowed(i, "Avond"):
                            if _DEBUG_VISIT_GEN:
                                _logger.info(
                                    "assign (pre-split) evening for proto=%s on %s->%s",
                                    getattr(p, "id", None),
                                    visits[i]["from_date"].isoformat(),
                                    visits[i]["to_date"].isoformat(),
                                )
                            break

    if _DEBUG_VISIT_GEN:
        _logger.info(
            "pre-split allowed parts: %s",
            [
                (
                    v["from_date"].isoformat(),
                    v["to_date"].isoformat(),
                    v.get("chosen_part_of_day"),
                    list(_compute_allowed_parts_for_entry(v["protocols"]) or []),
                )
                for v in visits_to_create
            ],
        )
    _assign_at_least_one(visits_to_create)

    # Split pass removed: forcing is applied at proto window parts for first index; keep visits as-is
    # Re-coalesce to ensure any exact-duplicate windows are merged
    if visits_to_create:
        visits_to_create = _coalesce_visits(visits_to_create)
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "post-assign visits: %s",
                [
                    (
                        v["from_date"].isoformat(),
                        v["to_date"].isoformat(),
                        v.get("chosen_part_of_day"),
                        [getattr(p, "id", None) for p in v["protocols"]],
                    )
                    for v in visits_to_create
                ],
            )

    # At-least-one part-of-day constraint assignment per protocol
    # Recompute allowed parts per entry as intersection across protocols
    def intersect_parts(a: set[str] | None, b: set[str] | None) -> set[str] | None:
        if a is None and b is None:
            return None
        if a is None:
            return b
        if b is None:
            return a
        return a & b

    allowed_parts_by_entry: dict[int, set[str] | None] = {}
    for idx, e in enumerate(visits_to_create):
        allowed: set[str] | None = None
        for p in e["protocols"]:
            allowed = intersect_parts(allowed, _derive_part_options(p))
        allowed_parts_by_entry[idx] = allowed

    # Helper to set chosen part if allowed
    def set_part_if_allowed(entry_idx: int, part: str) -> bool:
        allowed = allowed_parts_by_entry.get(entry_idx)
        if allowed is None or part in allowed:
            visits_to_create[entry_idx]["chosen_part_of_day"] = part
            return True
        return False

    # For each protocol, ensure at least one visit is morning/evening if required
    for p in protocols:
        # Collect entries containing this protocol
        entry_indexes = [
            i
            for i, e in enumerate(visits_to_create)
            if any(pp.id == p.id for pp in e["protocols"])
        ]
        if not entry_indexes:
            continue
        # Morning
        if getattr(p, "requires_morning_visit", False):
            satisfied = any(
                visits_to_create[i].get("chosen_part_of_day") == "Ochtend"
                for i in entry_indexes
            )
            if not satisfied:
                # pick earliest compatible
                picked = False
                for i in entry_indexes:
                    if set_part_if_allowed(i, "Ochtend"):
                        picked = True
                        if _DEBUG_VISIT_GEN:
                            _logger.info(
                                "assign morning part for proto=%s to visit %s->%s",
                                getattr(p, "id", None),
                                visits_to_create[i]["from_date"].isoformat(),
                                visits_to_create[i]["to_date"].isoformat(),
                            )
                        break
                if not picked and _DEBUG_VISIT_GEN:
                    _logger.warning(
                        "cannot satisfy requires_morning_visit for proto=%s; no morning-capable visit",
                        getattr(p, "id", None),
                    )
        # Evening
        if getattr(p, "requires_evening_visit", False):
            satisfied = any(
                visits_to_create[i].get("chosen_part_of_day") == "Avond"
                for i in entry_indexes
            )
            if not satisfied:
                picked = False
                for i in entry_indexes:
                    if set_part_if_allowed(i, "Avond"):
                        picked = True
                        if _DEBUG_VISIT_GEN:
                            _logger.info(
                                "assign evening part for proto=%s to visit %s->%s",
                                getattr(p, "id", None),
                                visits_to_create[i]["from_date"].isoformat(),
                                visits_to_create[i]["to_date"].isoformat(),
                            )
                        break
                if not picked and _DEBUG_VISIT_GEN:
                    _logger.warning(
                        "cannot satisfy requires_evening_visit for proto=%s; no evening-capable visit",
                        getattr(p, "id", None),
                    )

    # Assign stable per-protocol occurrence indices to each visit entry
    # This disambiguates identical window ranges by ordering visits chronologically.
    for pid, windows in proto_windows.items():
        # Build sorted unique groups by (wf, wt)
        groups: list[tuple[date, date]] = []
        seen_pairs: set[tuple[date, date]] = set()
        for _vidx, wf, wt, _parts, _pvw_id in sorted(
            windows, key=lambda w: (w[1], w[2])
        ):
            pair = (wf, wt)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                groups.append(pair)
        # counters per group
        counters: dict[tuple[date, date], int] = {g: 0 for g in groups}
        # all entries including this protocol, sorted by from_date
        entries = [
            e for e in visits_to_create if any(pp.id == pid for pp in e["protocols"])
        ]
        entries.sort(key=lambda e: e["from_date"])
        for e in entries:
            assigned = False
            for g in groups:
                wf, wt = g
                if wf <= e["from_date"] <= wt:
                    counters[g] += 1
                    e.setdefault("per_proto_index", {})[pid] = counters[g]
                    assigned = True
                    break
            if not assigned:
                # Fallback: assign running index outside declared groups
                e.setdefault("per_proto_index", {})[pid] = (
                    max(counters.values()) + 1 if counters else 1
                )

    # Relax single-protocol visits whose start dates are unnecessarily
    # constrained by earlier bucketing decisions, while respecting each
    # protocol's own visit windows and min-gap.
    _relax_single_protocol_visit_starts(
        visits_to_create=visits_to_create,
        proto_windows=proto_windows,
        proto_id_to_protocol=proto_id_to_protocol,
    )

    # Simple-mode for Pad-family protocols: one visit per protocol window
    # without combining or bucketing, but enforcing a family-level
    # min_period_between_visits across all Pad visits.
    pad_gap_days = 0
    for p in protocols:
        if not _is_exception_family_protocol(p):
            continue
        pad_gap_days = max(
            pad_gap_days,
            _unit_to_days(
                p.min_period_between_visits_value, p.min_period_between_visits_unit
            )
            or 0,
        )

    pad_windows: list[tuple[date, date, Protocol, set[str] | None, int]] = []
    for p in protocols:
        if not _is_exception_family_protocol(p):
            continue
        for _vidx, wf, wt, parts, pvw_id in proto_windows.get(p.id, []):
            if wf > wt:
                continue
            pad_windows.append((wf, wt, p, parts, pvw_id))

    if pad_windows:
        pad_windows.sort(key=lambda it: it[0])
        last_pad_from: date | None = None
        for wf, wt, p, parts, pvw_id in pad_windows:
            candidate_from = wf
            if last_pad_from is not None and pad_gap_days:
                from_with_gap = last_pad_from + timedelta(days=pad_gap_days)
                if from_with_gap > candidate_from:
                    candidate_from = from_with_gap
            if candidate_from > wt:
                if _DEBUG_VISIT_GEN:
                    _logger.warning(
                        "Pad simple-mode cannot place proto=%s within window %s->%s (min-gap or bounds)",
                        getattr(p, "id", None),
                        wf.isoformat(),
                        wt.isoformat(),
                    )
                continue
            visits_to_create.append(
                {
                    "from_date": candidate_from,
                    "to_date": wt,
                    "protocols": [p],
                    "chosen_part_of_day": None,
                    "proto_parts": {p.id: parts},
                    "proto_pvw_ids": {p.id: pvw_id},
                }
            )
            last_pad_from = candidate_from

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
        # duration: base on max protocol duration in minutes
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
        # For morning/evening, refine duration as span between earliest plausible start
        # and latest plausible end across all contributing protocols.
        calc_start_for_duration: int | None = None
        end_candidates_for_duration = [
            _derive_end_time_minutes(p)
            for p in protos
            if _derive_end_time_minutes(p) is not None
        ]
        start_candidates_for_duration = [
            _derive_start_time_minutes(p)
            for p in protos
            if _derive_start_time_minutes(p) is not None
        ]
        # Also derive starts from end constraints minus per-protocol duration
        starts_from_end_minus_duration: list[int] = []
        for p in protos:
            end_m = _derive_end_time_minutes(p)
            dur_h = getattr(p, "visit_duration_hours", None)
            if end_m is not None and dur_h is not None:
                starts_from_end_minus_duration.append(int(end_m - int(dur_h * 60)))
        if _DEBUG_VISIT_GEN:
            _logger.info(
                "duration inputs: part=%s start_refs=%s end_refs=%s starts_from_end=%s chosen_start(ref-only)=%s",
                part_of_day,
                start_candidates_for_duration,
                end_candidates_for_duration,
                starts_from_end_minus_duration,
                start_time,
            )

        # Morning: use explicit end constraints plus derived starts-from-end to
        # compute a span from earliest plausible start to latest end.
        if part_of_day == "Ochtend" and end_candidates_for_duration:
            all_start_candidates = (
                start_candidates_for_duration + starts_from_end_minus_duration
            )
            if all_start_candidates:
                calc_start_for_duration = int(min(all_start_candidates))
                latest_end = int(max(end_candidates_for_duration))
                new_duration = int(max(0, latest_end - calc_start_for_duration))
                if _DEBUG_VISIT_GEN:
                    _logger.info(
                        "duration calc (Ochtend): protos=%s start_candidates_all=%s picked_start=%s latest_end=%s -> duration=%s (prev=%s)",
                        [getattr(p, "id", None) for p in protos],
                        all_start_candidates,
                        calc_start_for_duration,
                        latest_end,
                        new_duration,
                        duration_min,
                    )
                duration_min = new_duration

        # Evening: use earliest explicit/derived start and latest plausible end,
        # where ends can come from explicit end refs or (start + duration).
        if part_of_day == "Avond" and start_candidates_for_duration:
            ends_from_start: list[int] = []
            for p in protos:
                s = _derive_start_time_minutes(p)
                dur_h = getattr(p, "visit_duration_hours", None)
                if s is not None and dur_h is not None:
                    ends_from_start.append(int(s + int(dur_h * 60)))

            all_end_candidates: list[int] = []
            if end_candidates_for_duration:
                all_end_candidates.extend(int(e) for e in end_candidates_for_duration)
            all_end_candidates.extend(ends_from_start)

            if all_end_candidates:
                earliest_start = int(min(start_candidates_for_duration))
                latest_end_all = int(max(all_end_candidates))
                new_duration = int(max(0, latest_end_all - earliest_start))
                if _DEBUG_VISIT_GEN:
                    _logger.info(
                        "duration calc (Avond): protos=%s start_candidates=%s end_candidates_all=%s earliest_start=%s latest_end=%s -> duration=%s (prev=%s)",
                        [getattr(p, "id", None) for p in protos],
                        start_candidates_for_duration,
                        all_end_candidates,
                        earliest_start,
                        latest_end_all,
                        new_duration,
                        duration_min,
                    )
                duration_min = new_duration
        # start time text: will be calculated from final part_of_day and earliest minutes
        start_time_text = None
        # remarks: select unique whitelisted phrases only (planning)
        remarks_texts = [
            p.visit_conditions_text for p in protos if p.visit_conditions_text
        ]
        extracted = _extract_whitelisted_remarks(remarks_texts)
        remarks_planning = " | ".join(extracted) if extracted else None

        # Build field remarks listing species per function when multiple functions are combined
        remarks_field = None
        try:
            # Map: function name -> { species abbr -> set(visit_indices) }
            fn_to_species_indices: dict[str, dict[str, set[int]]] = {}
            # Get pvw_ids for this visit
            current_pvw_ids = v.get("proto_pvw_ids", {})

            for p in protos:
                fn = getattr(getattr(p, "function", None), "name", None)
                sp = getattr(p, "species", None)
                if not fn or sp is None:
                    continue
                abbr = getattr(sp, "abbreviation", None) or getattr(sp, "name", None)
                if not abbr:
                    continue

                # Use assigned per-protocol index from pvw_id
                pvw_id = current_pvw_ids.get(p.id)
                idx = pvw_id_to_vidx.get(pvw_id) if pvw_id else None

                indices: set[int] = {idx} if idx is not None else {1}
                fn_to_species_indices.setdefault(fn, {}).setdefault(abbr, set()).update(
                    indices
                )

            if len(fn_to_species_indices) > 0:
                lines: list[str] = []
                for fn_name in sorted(fn_to_species_indices.keys()):
                    entries: list[str] = []
                    for abbr, idxs in sorted(
                        fn_to_species_indices[fn_name].items(), key=lambda x: x[0]
                    ):
                        idx_text = "/".join(str(i) for i in sorted(idxs))
                        entries.append(f"{abbr} ({idx_text})")
                    species_list = ", ".join(entries)
                    lines.append(f"{fn_name}: {species_list}")
                remarks_field = "\n".join(lines) if lines else None
        except Exception:
            # Be resilient; do not break visit creation due to remark formatting
            pass

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

        # No global forcing: part_of_day comes from chosen bucket assignment and constraint pass

        # If morning/evening is enforced or chosen, compute start as (earliest end) - (max duration)
        # Morning: prefer protocols with end_timing_reference == SUNRISE
        # Evening: prefer protocols with end_timing_reference == SUNSET
        if part_of_day in {"Ochtend", "Avond"}:
            # Candidates from end relative minutes
            end_candidates = [
                _derive_end_time_minutes(p)
                for p in protos
                if _derive_end_time_minutes(p) is not None
            ]
            # Candidates from start relative minutes
            start_candidates = [
                _derive_start_time_minutes(p)
                for p in protos
                if _derive_start_time_minutes(p) is not None
            ]
            # compute local minutes for text derivation only (do not persist minutes)
            local_start_minutes: int | None = None
            if part_of_day == "Ochtend":
                # Morning: Prefer the calculated start used for duration for consistent text.
                if calc_start_for_duration is not None:
                    local_start_minutes = int(calc_start_for_duration)
                    if _DEBUG_VISIT_GEN:
                        _logger.info(
                            "start_time_text (Ochtend): using picked_start=%s for text; duration_min=%s",
                            calc_start_for_duration,
                            duration_min,
                        )
                # Fallback to previous behavior: earliest end minus duration
                elif end_candidates and duration_min is not None:
                    earliest_end = min(end_candidates)
                    local_start_minutes = int(earliest_end - duration_min)
                # If no end-based info is available, fall back to earliest
                # derived start across protocols.
                elif start_candidates:
                    local_start_minutes = int(min(start_candidates))
            else:  # Avond
                # Evening: prefer earliest start across protocols; fall back to earliest end
                if start_candidates:
                    local_start_minutes = int(min(start_candidates))
                elif end_candidates:
                    local_start_minutes = int(min(end_candidates))
            if local_start_minutes is not None:
                start_time_text = derive_start_time_text_for_visit(
                    part_of_day, local_start_minutes
                )

        # Calculate a consistent textual description based on chosen part and minutes
        if start_time_text is None:
            start_time_text = derive_start_time_text_for_visit(part_of_day, None)

        # union of functions/species across combined protos
        _function_ids_set = sorted({p.function_id for p in protos})
        _species_ids_set = sorted({p.species_id for p in protos})

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
            remarks_planning=remarks_planning,
            remarks_field=remarks_field,
            requires_morning_visit=requires_morning,
            requires_evening_visit=requires_evening,
            requires_june_visit=requires_june,
            requires_maternity_period_visit=requires_maternity,
        )
        # assign derived attributes (persisted)
        visit.part_of_day = part_of_day
        setattr(visit, "start_time_text", start_time_text)
        next_nr += 1
        # attach relations from Protocol relations (dedup by id)
        by_func: dict[int | None, Function] = {}
        for p in protos:
            f = getattr(p, "function", None)
            if f is not None:
                by_func[getattr(f, "id", None)] = f
        visit.functions = list(by_func.values())

        by_spec: dict[int | None, Species] = {}
        for p in protos:
            s = getattr(p, "species", None)
            if s is not None:
                by_spec[getattr(s, "id", None)] = s
        visit.species = list(by_spec.values())

        # Attach ProtocolVisitWindows
        pvws: list[ProtocolVisitWindow] = []
        for p in protos:
            pvw_id = current_pvw_ids.get(p.id)
            if pvw_id:
                # Find the PVW object in the loaded protocol windows
                pvw = next((w for w in p.visit_windows if w.id == pvw_id), None)
                if pvw:
                    pvws.append(pvw)
        visit.protocol_visit_windows = pvws

        db.add(visit)
        created.append(visit)

    if _DEBUG_VISIT_GEN:
        try:
            _logger.info(
                "created visits: %s",
                [
                    (
                        v.from_date.isoformat(),
                        v.to_date.isoformat(),
                        getattr(v, "part_of_day", None),
                        [getattr(f, "id", None) for f in getattr(v, "functions", [])],
                    )
                    for v in created
                ],
            )
        except Exception:
            pass

    return created, warnings


async def resolve_protocols_for_combos(
    db: AsyncSession, combos: list[dict]
) -> list[Protocol]:
    """Resolve a distinct union of protocols for multiple species–function combos.

    Args:
        db: Async session.
        combos: List of dicts with keys 'function_ids' and 'species_ids'.

    Returns:
        Unique list of Protocol ORM instances with visit_windows/species/function eager-loaded.
    """

    if not combos:
        return []

    # Build disjunction across combos: (function_id IN fset AND species_id IN sset) OR ...
    predicates = []
    for c in combos:
        f_ids = list({int(x) for x in c.get("function_ids", [])})
        s_ids = list({int(x) for x in c.get("species_ids", [])})
        if not f_ids or not s_ids:
            continue
        predicates.append(
            and_(Protocol.function_id.in_(f_ids), Protocol.species_id.in_(s_ids))
        )
    if not predicates:
        return []

    stmt: Select[tuple[Protocol]] = (
        select(Protocol)
        .where(or_(*predicates))
        .options(
            selectinload(Protocol.visit_windows),
            selectinload(Protocol.species).selectinload(Species.family),
            selectinload(Protocol.function),
        )
    )
    return (await db.execute(stmt)).scalars().unique().all()


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
            start_time_text=v.start_time_text,
            expertise_level=v.expertise_level,
            wbc=v.wbc,
            fiets=v.fiets,
            hub=v.hub,
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

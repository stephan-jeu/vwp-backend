from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.species import Species
from app.models.visit import Visit


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


def _is_allowed_cross_family(_a: Protocol, _b: Protocol) -> bool:
    """Determine if a specific cross-family combination is allowed.

    Default implementation returns False (no cross-family grouping). Extend later with
    a curated allowlist.
    """

    return False


def _functions_in_allowed_set(function_ids: set[int], allowed: set[int]) -> bool:
    """Check whether a set of functions is a subset of an allowed set."""

    return function_ids.issubset(allowed)


def _allow_together(a: Protocol, b: Protocol) -> bool:
    """Compatibility check whether two protocols may be grouped.

    This is the main hook for future exception rules. Current defaults:
      - Allow grouping broadly to enable baseline combinations.
        Stricter family/function rules can be enforced later.

    Args:
        a: First protocol.
        b: Second protocol.

    Returns:
        True if protocols may be grouped together.
    """

    return True


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
) -> list[Visit]:
    """Generate visits for a cluster based on selected functions and species.

    This is an append-only operation: existing visits are left intact.
    Combination logic is intentionally conservative (minimal viable) and applies
    the "most restrictive" constraints when merging overlapping protocol windows.
    """

    if not function_ids or not species_ids:
        return []

    # Fetch all protocols for selected pairs and their windows (eager-load windows)
    stmt: Select[tuple[Protocol]] = (
        select(Protocol)
        .where(
            Protocol.function_id.in_(function_ids), Protocol.species_id.in_(species_ids)
        )
        .options(selectinload(Protocol.visit_windows))
    )
    protocols: list[Protocol] = (await db.execute(stmt)).scalars().unique().all()

    if not protocols:
        return []

    # Windows loaded via selectinload

    # Group by visit_index across protocols; within each index, form compatible buckets
    visits_to_create: list[dict] = []
    by_index: dict[int, list[Protocol]] = defaultdict(list)
    for p in protocols:
        if p.visit_windows:
            for w in p.visit_windows:
                by_index[w.visit_index].append(p)
        elif p.visits:
            for idx in range(1, (p.visits or 0) + 1):
                by_index[idx].append(p)

    for visit_index, protos in sorted(by_index.items()):
        # Optional custom recipe per visit_index
        recipe = _apply_custom_recipe_if_any(protos, visit_index)
        if recipe is not None and len(recipe) > 0:
            # Map each bucket to a combined visit using time window intersections
            for bucket in recipe:
                # compute shifted windows per protocol and combine
                windows: list[tuple[date, date]] = []
                per_proto_days = [
                    _unit_to_days(
                        p.min_period_between_visits_value,
                        p.min_period_between_visits_unit,
                    )
                    for p in bucket
                    if p is not None
                ]
                offset_days = (visit_index - 1) * (
                    max(per_proto_days) if per_proto_days else 0
                )
                for p in bucket:
                    w = next(
                        (w for w in p.visit_windows if w.visit_index == visit_index),
                        None,
                    )
                    if w is None:
                        continue
                    wf = _to_current_year(w.window_from) + timedelta(days=offset_days)
                    wt = _to_current_year(w.window_to) + timedelta(days=offset_days)
                    windows.append((wf, wt))
                if not windows:
                    continue
                from_date = max(w[0] for w in windows)
                to_date = min(w[1] for w in windows)
                if from_date > to_date:
                    # No common intersection for the recipe step; fall back to per-protocol
                    for p in bucket:
                        w = next(
                            (
                                w
                                for w in p.visit_windows
                                if w.visit_index == visit_index
                            ),
                            None,
                        )
                        if w is None:
                            continue
                        visits_to_create.append(
                            {
                                "from_date": _to_current_year(w.window_from)
                                + timedelta(days=offset_days),
                                "to_date": _to_current_year(w.window_to)
                                + timedelta(days=offset_days),
                                "protocols": [p],
                            }
                        )
                    continue
                visits_to_create.append(
                    {
                        "from_date": from_date,
                        "to_date": to_date,
                        "protocols": bucket,
                    }
                )
            continue

        # Generic path: derive shifted windows and attributes for this visit_index
        per_proto_days = [
            _unit_to_days(
                p.min_period_between_visits_value, p.min_period_between_visits_unit
            )
            for p in protos
            if p is not None
        ]
        offset_days = (visit_index - 1) * (max(per_proto_days) if per_proto_days else 0)

        entries: list[tuple[Protocol, tuple[date, date], str | None]] = []
        for p in protos:
            w = next((w for w in p.visit_windows if w.visit_index == visit_index), None)
            if w is None:
                continue
            wf = _to_current_year(w.window_from) + timedelta(days=offset_days)
            wt = _to_current_year(w.window_to) + timedelta(days=offset_days)
            if wf > wt:
                continue
            part = _derive_part_of_day(p)
            entries.append((p, (wf, wt), part))
        if not entries:
            continue

        # Split by part_of_day key first (keep None separate)
        by_part: dict[
            str | None, list[tuple[Protocol, tuple[date, date], str | None]]
        ] = defaultdict(list)
        for e in entries:
            by_part[e[2]].append(e)

        for _part_key, items in by_part.items():
            # Build overlap graph respecting exception compatibility
            indexed: list[tuple[int, Protocol, tuple[date, date]]] = [
                (i, it[0], it[1]) for i, it in enumerate(items)
            ]

            # Filter edges by both window overlap and _allow_together
            overlap_items: list[tuple[int, tuple[date, date]]] = [
                (i, win) for i, _p, win in indexed
            ]
            comps = _connected_components_by_overlap(overlap_items)

            for comp in comps:
                # Within component, further split by compatibility if needed
                comp_items = [indexed[i] for i in comp]

                # Greedy bucketing by compatibility
                buckets: list[list[tuple[int, Protocol, tuple[date, date]]]] = []
                for idx, proto, win in comp_items:
                    placed = False
                    for b in buckets:
                        if all(_allow_together(proto, other) for _i, other, _w in b):
                            b.append((idx, proto, win))
                            placed = True
                            break
                    if not placed:
                        buckets.append([(idx, proto, win)])

                for bucket in buckets:
                    wins = [w for _i, _p, w in bucket]
                    from_date = max(w[0] for w in wins)
                    to_date = min(w[1] for w in wins)
                    if from_date > to_date:
                        # fallback to single-protocol visits inside this bucket
                        for _i, p, (wf, wt) in bucket:
                            visits_to_create.append(
                                {
                                    "from_date": wf,
                                    "to_date": wt,
                                    "protocols": [p],
                                }
                            )
                        continue
                    visits_to_create.append(
                        {
                            "from_date": from_date,
                            "to_date": to_date,
                            "protocols": [p for _i, p, _w in bucket],
                        }
                    )

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
        # part of day: consistent value or None
        part_values = [
            _derive_part_of_day(p) for p in protos if _derive_part_of_day(p) is not None
        ]
        part_of_day = part_values[0] if part_values else None
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

    return created


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

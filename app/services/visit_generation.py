from __future__ import annotations

import logging
import os
from uuid import uuid4

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.species import Species
from app.models.visit import Visit

from .visit_generation_ortools import generate_visits_cp_sat

_DEBUG_VISIT_GEN = os.getenv("VISIT_GEN_DEBUG", "").lower() in {"1", "true", "yes"}
_logger = logging.getLogger("uvicorn.error")


async def generate_visits_for_cluster(
    db: AsyncSession,
    cluster: Cluster,
    function_ids: list[int],
    species_ids: list[int],
    *,
    protocols: list[Protocol] | None = None,
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
    """Generate visits for a cluster based on selected functions and species.

    Delegates to the Graph-Based/CP-SAT Constraint Satisfaction solver.
    """
    if _DEBUG_VISIT_GEN:
        _logger.info(
            "visit_gen start cluster=%s functions=%s species=%s",
            getattr(cluster, "id", None),
            function_ids,
            species_ids,
        )

    # Resolve protocols if not provided
    if protocols is None:
        if not function_ids or not species_ids:
            return [], []

        stmt = (
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

    # Delegate to CP-SAT solver implementation.
    return await generate_visits_cp_sat(
        db,
        cluster,
        protocols,
        default_required_researchers=default_required_researchers,
        default_preferred_researcher_id=default_preferred_researcher_id,
        default_expertise_level=default_expertise_level,
        default_wbc=default_wbc,
        default_fiets=default_fiets,
        default_hub=default_hub,
        default_dvp=default_dvp,
        default_sleutel=default_sleutel,
        default_remarks_field=default_remarks_field,
    )


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

    stmt = (
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
                .options(
                    selectinload(Visit.functions),
                    selectinload(Visit.species),
                    selectinload(Visit.protocol_visit_windows),
                )
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
        clone.protocol_visit_windows = list(v.protocol_visit_windows or [])
        db.add(clone)

    return new_cluster


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

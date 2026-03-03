from __future__ import annotations

from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.visit import Visit, visit_protocol_visit_windows


async def sync_cluster_pvw_links(db: AsyncSession, cluster_id: int) -> None:
    """Recalculate and correct protocol-visit-window links for all active visits in a cluster.

    Should be called after any operation that changes the set of active visits
    in a cluster (deletion, creation) so that remaining visits have correct PVW links.

    Args:
        db: Async SQLAlchemy session.
        cluster_id: Cluster to synchronise.
    """

    stmt = (
        select(Visit)
        .where(Visit.cluster_id == cluster_id, Visit.deleted_at.is_(None))
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.protocol_visit_windows),
        )
        .order_by(Visit.visit_nr)
    )
    visits = (await db.execute(stmt)).scalars().all()
    if not visits:
        return

    function_ids = {f.id for v in visits for f in v.functions if f.id is not None}
    species_ids = {s.id for v in visits for s in v.species if s.id is not None}
    if not function_ids or not species_ids:
        return

    protocols = (
        await db.execute(
            select(Protocol).where(
                Protocol.function_id.in_(function_ids),
                Protocol.species_id.in_(species_ids),
            )
        )
    ).scalars().all()

    protocol_map: dict[tuple[int, int], Protocol] = {
        (p.function_id, p.species_id): p
        for p in protocols
        if p.function_id is not None and p.species_id is not None
    }
    if not protocol_map:
        return

    inserts: list[dict[str, int]] = []
    deletes: list[tuple[int, int]] = []
    counters: dict[tuple[int, int], int] = {}

    for visit in visits:
        if visit.visit_nr is None:
            continue
        if visit.custom_function_name or visit.custom_species_name:
            continue

        v_function_ids = [f.id for f in visit.functions if f.id is not None]
        v_species_ids = [s.id for s in visit.species if s.id is not None]
        if not v_function_ids or not v_species_ids:
            continue

        # Compute expected PVW IDs using current counters (before incrementing)
        expected_ids: set[int] = set()
        for func_id in v_function_ids:
            for species_id in v_species_ids:
                protocol = protocol_map.get((func_id, species_id))
                if not protocol:
                    continue
                visit_index = counters.get((func_id, species_id), 0) + 1
                pvw_id = (
                    await db.execute(
                        select(ProtocolVisitWindow.id).where(
                            ProtocolVisitWindow.protocol_id == protocol.id,
                            ProtocolVisitWindow.visit_index == visit_index,
                        )
                    )
                ).scalar_one_or_none()
                if pvw_id is not None:
                    expected_ids.add(pvw_id)

        # Increment counters: this visit counts as a "prior" for subsequent visits
        for func_id in v_function_ids:
            for species_id in v_species_ids:
                if (func_id, species_id) in protocol_map:
                    counters[(func_id, species_id)] = (
                        counters.get((func_id, species_id), 0) + 1
                    )

        if not expected_ids:
            continue

        existing_ids = {pvw.id for pvw in visit.protocol_visit_windows if pvw.id is not None}

        for pvw_id in expected_ids - existing_ids:
            inserts.append({"visit_id": visit.id, "protocol_visit_window_id": pvw_id})
        for pvw_id in existing_ids - expected_ids:
            deletes.append((visit.id, pvw_id))

    if inserts:
        await db.execute(insert(visit_protocol_visit_windows), inserts)

    if deletes:
        await db.execute(
            delete(visit_protocol_visit_windows).where(
                tuple_(
                    visit_protocol_visit_windows.c.visit_id,
                    visit_protocol_visit_windows.c.protocol_visit_window_id,
                ).in_(deletes)
            )
        )

    if inserts or deletes:
        logger.debug(
            "sync_cluster_pvw_links cluster_id=%s: added %s, removed %s PVW links.",
            cluster_id,
            len(inserts),
            len(deletes),
        )

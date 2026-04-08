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
        (
            await db.execute(
                select(Protocol).where(
                    Protocol.function_id.in_(function_ids),
                    Protocol.species_id.in_(species_ids),
                )
            )
        )
        .scalars()
        .all()
    )

    protocol_map: dict[tuple[int, int], Protocol] = {
        (p.function_id, p.species_id): p
        for p in protocols
        if p.function_id is not None and p.species_id is not None
    }
    if not protocol_map:
        return

    # Preload all PVWs for relevant protocols, sorted by visit_index.
    protocol_ids = {p.id for p in protocol_map.values()}
    all_pvws: list[ProtocolVisitWindow] = (
        (
            await db.execute(
                select(ProtocolVisitWindow).where(
                    ProtocolVisitWindow.protocol_id.in_(protocol_ids)
                )
            )
        )
        .scalars()
        .all()
    )

    protocol_pvws: dict[int, list[ProtocolVisitWindow]] = {}
    for pvw in all_pvws:
        protocol_pvws.setdefault(pvw.protocol_id, []).append(pvw)
    for pid in protocol_pvws:
        protocol_pvws[pid].sort(key=lambda p: p.visit_index)

    # Build per-visit index of exact (function_id, species_id) pairs.
    # This avoids the Cartesian-product bug where a combined-protocol visit
    # (e.g. Baardvleermuis/Paarverblijf + GD/Massawinterverblijfplaats) would
    # also match the spurious (GD/Paarverblijf) protocol when iterating
    # v_function_ids × v_species_ids.
    visit_fs: dict[int, set[tuple[int, int]]] = {}
    for v in visits:
        pairs: set[tuple[int, int]] = set()
        for f in v.functions:
            for s in v.species:
                if f.id is not None and s.id is not None:
                    pairs.add((f.id, s.id))
        visit_fs[v.id] = pairs

    # Protocol-centric assignment: for each protocol find the ordered list of
    # visits that carry that exact (function, species) pair, then assign
    # pvw[i] (sorted by visit_index) to visit[i] (sorted by visit_nr).
    expected: dict[int, set[int]] = {v.id: set() for v in visits}

    for (func_id, species_id), protocol in protocol_map.items():
        pvws = protocol_pvws.get(protocol.id, [])
        if not pvws:
            continue

        matching_visits = [
            v for v in visits  # already ordered by visit_nr
            if (func_id, species_id) in visit_fs.get(v.id, set())
            and not v.custom_function_name
            and not v.custom_species_name
            and v.visit_nr is not None
        ]

        for i, visit in enumerate(matching_visits):
            if i < len(pvws) and pvws[i].id is not None:
                expected[visit.id].add(pvws[i].id)

    inserts: list[dict[str, int]] = []
    deletes: list[tuple[int, int]] = []

    for visit in visits:
        existing_ids = {
            pvw.id for pvw in visit.protocol_visit_windows if pvw.id is not None
        }
        exp_ids = expected.get(visit.id, set())

        for pvw_id in exp_ids - existing_ids:
            inserts.append({"visit_id": visit.id, "protocol_visit_window_id": pvw_id})
        for pvw_id in existing_ids - exp_ids:
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

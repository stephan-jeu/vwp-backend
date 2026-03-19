from __future__ import annotations

from datetime import date

from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.visit import Visit, visit_protocol_visit_windows


def _month_day_overlap_days(
    visit_from: date,
    visit_to: date,
    pvw_from: date,
    pvw_to: date,
) -> int:
    """Compute overlap in days between a visit's date range and a pvw template window.

    Year is ignored — only month and day are compared (pvw windows use a
    canonical year like 2000).

    Args:
        visit_from: Visit start date.
        visit_to: Visit end date.
        pvw_from: PVW template window start date.
        pvw_to: PVW template window end date.

    Returns:
        Number of overlapping days (0 if no overlap).
    """
    try:
        vf = date(2000, visit_from.month, visit_from.day)
        vt = date(2000, visit_to.month, visit_to.day)
        pf = date(2000, pvw_from.month, pvw_from.day)
        pt = date(2000, pvw_to.month, pvw_to.day)
    except ValueError:
        return 0
    start = max(vf, pf)
    end = min(vt, pt)
    return max(0, (end - start).days + 1)


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

    # Preload all PVWs for relevant protocols to enable window-overlap matching.
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

    inserts: list[dict[str, int]] = []
    deletes: list[tuple[int, int]] = []
    counters: dict[tuple[int, int], int] = {}
    # Track all pvw IDs already claimed by earlier visits in this cluster to
    # prevent the same PVW from being assigned to more than one visit.
    claimed_pvws: dict[int, set[int]] = {}

    for visit in visits:
        if visit.visit_nr is None:
            continue
        if visit.custom_function_name or visit.custom_species_name:
            continue

        v_function_ids = [f.id for f in visit.functions if f.id is not None]
        v_species_ids = [s.id for s in visit.species if s.id is not None]
        if not v_function_ids or not v_species_ids:
            continue

        # Compute expected PVW IDs (before incrementing counters).
        expected_ids: set[int] = set()
        for func_id in v_function_ids:
            for species_id in v_species_ids:
                protocol = protocol_map.get((func_id, species_id))
                if not protocol:
                    continue
                pvws = protocol_pvws.get(protocol.id, [])
                pvw_id = None

                # Primary: match by date-window overlap (ignoring year).
                # Prefer unclaimed PVWs; fall back to best overall only when
                # every candidate PVW has already been claimed by an earlier visit.
                if visit.from_date and visit.to_date:
                    already_claimed = claimed_pvws.get(protocol.id, set())
                    best_pvw_id = None
                    best_overlap = 0
                    best_unclaimed_pvw_id = None
                    best_unclaimed_overlap = 0
                    for pvw in pvws:
                        if pvw.window_from and pvw.window_to:
                            overlap = _month_day_overlap_days(
                                visit.from_date,
                                visit.to_date,
                                pvw.window_from,
                                pvw.window_to,
                            )
                            if overlap > 0:
                                if pvw.id not in already_claimed and overlap > best_unclaimed_overlap:
                                    best_unclaimed_overlap = overlap
                                    best_unclaimed_pvw_id = pvw.id
                                if overlap > best_overlap:
                                    best_overlap = overlap
                                    best_pvw_id = pvw.id
                    chosen = best_unclaimed_pvw_id if best_unclaimed_pvw_id is not None else best_pvw_id
                    if chosen is not None:
                        pvw_id = chosen
                        claimed_pvws.setdefault(protocol.id, set()).add(chosen)

                # Fallback: positional ordering (original behaviour) for visits
                # that lack date windows or whose window matches no pvw.
                if pvw_id is None:
                    visit_index = counters.get((func_id, species_id), 0) + 1
                    for pvw in pvws:
                        if pvw.visit_index == visit_index:
                            pvw_id = pvw.id
                            break

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

        existing_ids = {
            pvw.id for pvw in visit.protocol_visit_windows if pvw.id is not None
        }

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

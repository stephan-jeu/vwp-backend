from __future__ import annotations

from datetime import date

from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.db.utils import select_active
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


def _protocol_key(protocol: Protocol) -> tuple[int, int] | None:
    """Return the protocol key used for mapping PVW links.

    Args:
        protocol: Protocol entity.

    Returns:
        Tuple of (function_id, species_id) if available, otherwise None.
    """

    if protocol.function_id is None or protocol.species_id is None:
        return None
    return (protocol.function_id, protocol.species_id)


async def backfill_visit_protocol_visit_windows(session: AsyncSession) -> None:
    """Backfill missing protocol-visit-window links for non-custom visits.

    Visits without functions or species (typically custom visits) are ignored.
    The expected PVWs are derived from protocol-specific visit ordering within
    each cluster.

    Args:
        session: Async SQLAlchemy session.

    Returns:
        None.
    """

    stmt = select_active(Visit).options(
        selectinload(Visit.functions),
        selectinload(Visit.species),
        selectinload(Visit.protocol_visit_windows),
    )
    visits = (await session.execute(stmt)).scalars().all()
    if not visits:
        logger.info("No visits found.")
        return

    function_ids = {
        f.id for visit in visits for f in visit.functions if f.id is not None
    }
    species_ids = {s.id for visit in visits for s in visit.species if s.id is not None}

    protocol_map: dict[tuple[int, int], Protocol] = {}
    if function_ids and species_ids:
        stmt_protocols = select(Protocol).where(
            Protocol.function_id.in_(function_ids),
            Protocol.species_id.in_(species_ids),
        )
        protocols = (await session.execute(stmt_protocols)).scalars().all()
        protocol_map = {
            key: protocol
            for protocol in protocols
            if (key := _protocol_key(protocol)) is not None
        }

    # Preload all PVWs for relevant protocols to enable window-overlap matching.
    protocol_ids = {p.id for p in protocol_map.values()}
    all_pvws: list[ProtocolVisitWindow] = []
    if protocol_ids:
        all_pvws = (
            (
                await session.execute(
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

    visits_by_cluster: dict[int, list[Visit]] = {}
    for visit in visits:
        visits_by_cluster.setdefault(visit.cluster_id, []).append(visit)
    for cluster_visits in visits_by_cluster.values():
        cluster_visits.sort(key=lambda v: v.visit_nr or 0)

    inserts: list[dict[str, int]] = []
    deletes: list[tuple[int, int]] = []
    total_checked = 0
    total_missing = 0
    total_stale = 0
    skipped_custom = 0
    skipped_no_visit_nr = 0
    skipped_no_relations = 0

    for cluster_visits_list in visits_by_cluster.values():
        counters: dict[tuple[int, int], int] = {}
        # Track pvw IDs claimed via tie-breaking to avoid re-use within this cluster.
        claimed_tie_pvws: dict[int, set[int]] = {}

        for visit in cluster_visits_list:
            if visit.custom_function_name or visit.custom_species_name:
                skipped_custom += 1
                continue
            if visit.visit_nr is None:
                skipped_no_visit_nr += 1
                continue
            if not visit.functions or not visit.species:
                skipped_no_relations += 1
                continue

            function_ids = [f.id for f in visit.functions if f.id is not None]
            species_ids = [s.id for s in visit.species if s.id is not None]
            if not function_ids or not species_ids:
                continue

            total_checked += 1

            expected_ids: set[int] = set()
            for func_id in function_ids:
                for species_id in species_ids:
                    protocol = protocol_map.get((func_id, species_id))
                    if not protocol:
                        continue
                    pvws = protocol_pvws.get(protocol.id, [])
                    pvw_id = None

                    # Primary: match by date-window overlap (ignoring year).
                    # This correctly handles clusters where multiple visits of the
                    # same protocol share a date range rather than relying on
                    # visit_nr position alone.
                    if visit.from_date and visit.to_date:
                        best_pvw_id = None
                        best_overlap = 0
                        tied_pvws: list[ProtocolVisitWindow] = []
                        for pvw in pvws:
                            if pvw.window_from and pvw.window_to:
                                overlap = _month_day_overlap_days(
                                    visit.from_date,
                                    visit.to_date,
                                    pvw.window_from,
                                    pvw.window_to,
                                )
                                if overlap > best_overlap:
                                    best_overlap = overlap
                                    best_pvw_id = pvw.id
                                    tied_pvws = [pvw]
                                elif overlap == best_overlap and overlap > 0:
                                    tied_pvws.append(pvw)
                        # Tiebreaker: when multiple pvws share the same best overlap
                        # (e.g. identical windows), pick the first unclaimed pvw.
                        if len(tied_pvws) > 1:
                            already_claimed = claimed_tie_pvws.get(protocol.id, set())
                            for pvw in tied_pvws:
                                if pvw.id not in already_claimed:
                                    best_pvw_id = pvw.id
                                    break
                        if best_pvw_id is not None:
                            pvw_id = best_pvw_id
                            if len(tied_pvws) > 1:
                                claimed_tie_pvws.setdefault(protocol.id, set()).add(
                                    pvw_id
                                )

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

            # Increment counters for the fallback path of subsequent visits.
            for func_id in function_ids:
                for species_id in species_ids:
                    if (func_id, species_id) in protocol_map:
                        counters[(func_id, species_id)] = (
                            counters.get((func_id, species_id), 0) + 1
                        )

            if not expected_ids:
                continue

            existing_ids = {
                pvw.id for pvw in visit.protocol_visit_windows if pvw.id is not None
            }
            missing_ids = expected_ids - existing_ids
            if missing_ids:
                total_missing += len(missing_ids)
                for pvw_id in missing_ids:
                    inserts.append(
                        {"visit_id": visit.id, "protocol_visit_window_id": pvw_id}
                    )

            stale_ids = existing_ids - expected_ids
            if stale_ids:
                total_stale += len(stale_ids)
                for pvw_id in stale_ids:
                    deletes.append((visit.id, pvw_id))

    if inserts:
        await session.execute(insert(visit_protocol_visit_windows), inserts)

    if deletes:
        await session.execute(
            delete(visit_protocol_visit_windows).where(
                tuple_(
                    visit_protocol_visit_windows.c.visit_id,
                    visit_protocol_visit_windows.c.protocol_visit_window_id,
                ).in_(deletes)
            )
        )

    if inserts or deletes:
        await session.commit()

    logger.info(
        "Checked %s visits: added %s missing PVW links, removed %s stale PVW links.",
        total_checked,
        total_missing,
        total_stale,
    )
    logger.info(
        "Skipped %s custom visits, %s without visit_nr, %s without species/functions.",
        skipped_custom,
        skipped_no_visit_nr,
        skipped_no_relations,
    )

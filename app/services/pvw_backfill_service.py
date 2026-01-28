from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.visit import Visit, visit_protocol_visit_windows


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

    stmt = select(Visit).options(
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

    visits_by_cluster: dict[int, list[Visit]] = {}
    for visit in visits:
        visits_by_cluster.setdefault(visit.cluster_id, []).append(visit)
    for cluster_visits in visits_by_cluster.values():
        cluster_visits.sort(key=lambda v: v.visit_nr or 0)

    inserts: list[dict[str, int]] = []
    total_checked = 0
    total_missing = 0
    skipped_custom = 0
    skipped_no_visit_nr = 0
    skipped_no_relations = 0

    for visit in visits:
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

        counters: dict[tuple[int, int], int] = {}
        cluster_visits = visits_by_cluster.get(visit.cluster_id, [])
        for clustered_visit in cluster_visits:
            if clustered_visit.id == visit.id:
                break
            if (
                clustered_visit.custom_function_name
                or clustered_visit.custom_species_name
            ):
                continue
            if clustered_visit.visit_nr is None:
                continue
            prior_function_ids = [
                f.id for f in clustered_visit.functions if f.id is not None
            ]
            prior_species_ids = [
                s.id for s in clustered_visit.species if s.id is not None
            ]
            for func_id in prior_function_ids:
                for species_id in prior_species_ids:
                    if (func_id, species_id) in protocol_map:
                        counters[(func_id, species_id)] = (
                            counters.get((func_id, species_id), 0) + 1
                        )

        expected_ids: set[int] = set()
        for func_id in function_ids:
            for species_id in species_ids:
                protocol = protocol_map.get((func_id, species_id))
                if not protocol:
                    continue
                visit_index = counters.get((func_id, species_id), 0) + 1
                stmt_pvw = select(ProtocolVisitWindow.id).where(
                    ProtocolVisitWindow.protocol_id == protocol.id,
                    ProtocolVisitWindow.visit_index == visit_index,
                )
                pvw_id = (await session.execute(stmt_pvw)).scalar_one_or_none()
                if pvw_id is not None:
                    expected_ids.add(pvw_id)

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

    if inserts:
        await session.execute(insert(visit_protocol_visit_windows), inserts)
        await session.commit()
        logger.info(
            "Backfilled %s missing PVW links across %s visits.",
            total_missing,
            total_checked,
        )
    else:
        logger.info("No missing PVW links found across %s visits.", total_checked)

    logger.info(
        "Skipped %s custom visits, %s without visit_nr, %s without species/functions.",
        skipped_custom,
        skipped_no_visit_nr,
        skipped_no_relations,
    )

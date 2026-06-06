from __future__ import annotations

from datetime import date

from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.visit import Visit, visit_protocol_visit_windows
from app.services.visit_generation_common import _derive_part_of_day


async def sync_cluster_pvw_links(db: AsyncSession, cluster_id: int) -> tuple[int, int]:
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
        .execution_options(populate_existing=True)
    )
    visits = (await db.execute(stmt)).scalars().all()
    if not visits:
        return 0, 0

    function_ids = {f.id for v in visits for f in v.functions if f.id is not None}
    species_ids = {s.id for v in visits for s in v.species if s.id is not None}
    if not function_ids or not species_ids:
        return 0, 0

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

    protocol_map: dict[tuple[int, int, str | None], Protocol] = {
        (p.function_id, p.species_id, p.start_timing_reference): p
        for p in protocols
        if p.function_id is not None and p.species_id is not None
    }
    if not protocol_map:
        return 0, 0

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

    # Build reverse map of existing pvw links: pvw_id → set of visit_ids.
    # Used to preserve valid existing links and avoid unnecessary reassignment.
    pvw_to_visits: dict[int, set[int]] = {}
    for v in visits:
        for existing_pvw in v.protocol_visit_windows:
            if existing_pvw.id is not None:
                pvw_to_visits.setdefault(existing_pvw.id, set()).add(v.id)

    # Map pvw_id → protocol_id, and protocol_id → (func_id, species_id).
    # Used to guard against deleting links for protocols with no matching
    # visits (e.g. daypart mismatch between protocol and visit).
    pvw_protocol_id: dict[int, int] = {
        pvw.id: pvw.protocol_id for pvw in all_pvws if pvw.id is not None
    }
    protocol_fs: dict[int, tuple[int, int]] = {
        p.id: (p.function_id, p.species_id)
        for p in protocol_map.values()
        if p.function_id is not None and p.species_id is not None
    }
    # Tracks pvw_ids that were actively placed (preserved or newly assigned).
    # Used in the delete guard: only delete a pvw link if the pvw was placed
    # somewhere (possibly on a different visit).  Skipped pvw's (no eligible
    # visit found) should not cause existing links to be removed as long as
    # the visit still carries the (func, species) pair.
    placed_pvws: set[int] = set()

    # Count how many protocols exist per (func_id, species_id) pair.
    # When there is only one protocol for a pair, daypart is a preference and
    # we can fall back to all eligible visits.  When there are multiple
    # protocols for the same pair (e.g. independent Ochtend / Avond protocols),
    # the daypart is the hard separator and we must NOT mix visits across them.
    fs_protocol_count: dict[tuple[int, int], int] = {}
    for func_id_k, species_id_k, _ in protocol_map:
        k = (func_id_k, species_id_k)
        fs_protocol_count[k] = fs_protocol_count.get(k, 0) + 1

    # Protocol-centric assignment: for each pvw, preserve an existing valid link
    # if exactly one matching visit already holds it. Otherwise find the best
    # eligible visit by window overlap: earliest visit for the first pvw,
    # latest for the last pvw. Within equal position, prefer highest overlap.
    expected: dict[int, set[int]] = {v.id: set() for v in visits}

    for (func_id, species_id, _), protocol in protocol_map.items():
        pvws = protocol_pvws.get(protocol.id, [])
        if not pvws:
            continue

        expected_part = _derive_part_of_day(protocol)
        _base_visits = [
            v for v in visits  # already ordered by visit_nr
            if (func_id, species_id) in visit_fs.get(v.id, set())
            and not v.custom_function_name
            and not v.custom_species_name
            and v.visit_nr is not None
        ]
        _daypart_visits = [
            v for v in _base_visits
            if expected_part is None or v.part_of_day == expected_part
        ]
        # Fall back to all eligible visits only when this is the sole protocol
        # for the (func, species) pair — if multiple protocols share the pair,
        # each owns a specific daypart and the hard filter must be kept.
        _sole_protocol = fs_protocol_count.get((func_id, species_id), 1) == 1
        matching_visits = _daypart_visits if (_daypart_visits or not _sole_protocol) else _base_visits

        assigned: set[int] = set()
        last_pvw_idx = len(pvws) - 1
        matching_visit_ids = {v.id for v in matching_visits}

        for i, pvw in enumerate(pvws):
            if pvw.id is None:
                continue

            raw_linked = pvw_to_visits.get(pvw.id, set())
            if raw_linked and not (raw_linked & matching_visit_ids):
                # Pvw has existing cluster links but none to currently matching
                # visits (those visits lost the func/species).  Don't reassign
                # to another visit — the cleanup phase will delete the stale link.
                # Reassigning would create unwanted duplicate index entries.
                continue

            # Preserve an existing link when exactly one valid, unassigned visit
            # already holds this pvw. Duplicates (2+) and missing (0) fall
            # through to the overlap-based selection below.
            existing_linked = raw_linked & matching_visit_ids - assigned
            if len(existing_linked) == 1:
                visit_id = next(iter(existing_linked))
                expected[visit_id].add(pvw.id)
                assigned.add(visit_id)
                placed_pvws.add(pvw.id)
                continue

            # Project pvw window to the first eligible visit's year so that
            # the overlap comparison works regardless of the reference year
            # used in pvw windows (typically 2000).
            def _project_pvw(v: Visit) -> tuple[date, date] | None:
                if v.from_date is None:
                    return None
                year = v.from_date.year
                try:
                    return (
                        pvw.window_from.replace(year=year),
                        pvw.window_to.replace(year=year),
                    )
                except ValueError:
                    return None

            def _overlap_days(v: Visit) -> int:
                proj = _project_pvw(v)
                if proj is None or v.from_date is None or v.to_date is None:
                    return 0
                pvw_from, pvw_to = proj
                return max(
                    0,
                    (min(v.to_date, pvw_to) - max(v.from_date, pvw_from)).days + 1,
                )

            eligible = [
                v for v in matching_visits
                if v.id not in assigned
                and v.from_date is not None
                and v.to_date is not None
                and _overlap_days(v) > 0
            ]
            if not eligible:
                # Fallback: ignore window check to preserve original behaviour
                eligible = [v for v in matching_visits if v.id not in assigned]
            if not eligible:
                continue
            if i == last_pvw_idx:
                eligible.sort(key=lambda v: (
                    0 if expected_part is None or v.part_of_day == expected_part else 1,
                    -v.to_date.toordinal(),
                    -_overlap_days(v),
                ))
            else:
                eligible.sort(key=lambda v: (
                    0 if expected_part is None or v.part_of_day == expected_part else 1,
                    v.from_date.toordinal(),
                    -_overlap_days(v),
                ))
            chosen = eligible[0]
            expected[chosen.id].add(pvw.id)
            assigned.add(chosen.id)
            placed_pvws.add(pvw.id)

    # Snapshot of existing pvw links per visit (before any mutations this run).
    visit_existing_pvw_ids: dict[int, set[int]] = {
        v.id: {p.id for p in v.protocol_visit_windows if p.id is not None}
        for v in visits
    }

    inserts: list[dict[str, int]] = []
    deletes: list[tuple[int, int]] = []

    for visit in visits:
        existing_ids = visit_existing_pvw_ids[visit.id]
        exp_ids = expected.get(visit.id, set())

        for pvw_id in exp_ids - existing_ids:
            inserts.append({"visit_id": visit.id, "protocol_visit_window_id": pvw_id})
        for pvw_id in existing_ids - exp_ids:
            if pvw_id not in placed_pvws:
                # Pvw was not actively placed (skipped — more pvws than eligible
                # visits for this protocol). Only delete if the visit no longer
                # carries the (func, species) pair — i.e. the SFC was removed.
                proto_id = pvw_protocol_id.get(pvw_id)
                fs_pair = protocol_fs.get(proto_id)
                if fs_pair is None or fs_pair in visit_fs.get(visit.id, set()):
                    continue
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
        logger.info(
            "sync_cluster_pvw_links cluster_id=%s: added %s, removed %s PVW links.",
            cluster_id,
            len(inserts),
            len(deletes),
        )
    return len(inserts), len(deletes)

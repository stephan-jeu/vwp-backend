from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.visit import Visit


def _unit_to_days(val: int | None, unit: str | None) -> int:
    if not val or not unit:
        return 0
    if unit == "days":
        return val
    if unit == "weeks":
        return val * 7
    if unit == "months":
        return val * 30  # Approx
    return 0


async def update_subsequent_visits(
    db: AsyncSession,
    executed_visit: Visit,
    execution_date: date,
) -> None:
    """Update the from_date of subsequent visits.

    The update is based on the executed visit's date and the protocol's
    minimum period between visits.
    """
    logger.debug(
        "update_subsequent_visits: start for visit_id=%s execution_date=%s",
        executed_visit.id,
        execution_date.isoformat(),
    )

    # Reload visit with PVWs and their protocols
    stmt = (
        select(Visit)
        .where(Visit.id == executed_visit.id)
        .options(
            selectinload(Visit.protocol_visit_windows).selectinload(
                ProtocolVisitWindow.protocol
            )
        )
    )
    visit = (await db.execute(stmt)).scalars().first()
    if not visit:
        logger.debug(
            "update_subsequent_visits: no visit reloaded for id=%s",
            executed_visit.id,
        )
        return

    if not visit.protocol_visit_windows:
        logger.debug(
            "update_subsequent_visits: visit_id=%s has no protocol_visit_windows",
            visit.id,
        )
        return

    updated_visit_ids: set[int] = set()

    for pvw in visit.protocol_visit_windows:
        protocol = pvw.protocol
        if not protocol:
            logger.debug(
                "update_subsequent_visits: skipping PVW id=%s for visit_id=%s because protocol is None",
                pvw.id,
                visit.id,
            )
            continue

        min_gap_days = _unit_to_days(
            protocol.min_period_between_visits_value,
            protocol.min_period_between_visits_unit,
        )
        if min_gap_days <= 0:
            logger.debug(
                "update_subsequent_visits: protocol_id=%s has non-positive min_gap_days=%s; skipping",
                protocol.id,
                min_gap_days,
            )
            continue

        current_idx = pvw.visit_index

        # Find subsequent PVWs for this protocol
        subsequent_pvws_stmt = (
            select(ProtocolVisitWindow)
            .where(
                ProtocolVisitWindow.protocol_id == protocol.id,
                ProtocolVisitWindow.visit_index > current_idx,
            )
            .order_by(ProtocolVisitWindow.visit_index)
        )
        subsequent_pvws = (await db.execute(subsequent_pvws_stmt)).scalars().all()

        if not subsequent_pvws:
            logger.debug(
                "update_subsequent_visits: no subsequent PVWs for protocol_id=%s current_idx=%s",
                protocol.id,
                current_idx,
            )
            continue

        subsequent_pvw_ids = [w.id for w in subsequent_pvws]

        # Find visits linked to these subsequent PVWs
        # Note: A visit might be linked to multiple PVWs (combined visit).
        # We update if ANY of its linked PVWs requires a push.
        # Here we focus on the specific protocol chain.

        linked_visits_stmt = (
            select(Visit)
            .join(Visit.protocol_visit_windows)
            .where(
                Visit.cluster_id == visit.cluster_id,  # Same cluster
                ProtocolVisitWindow.id.in_(subsequent_pvw_ids),
                Visit.id != visit.id,  # Should be redundant but safe
            )
            .options(selectinload(Visit.protocol_visit_windows))
        )
        linked_visits = (await db.execute(linked_visits_stmt)).scalars().unique().all()

        if not linked_visits:
            logger.debug(
                "update_subsequent_visits: no linked subsequent visits for protocol_id=%s cluster_id=%s pvw_ids=%s",
                protocol.id,
                visit.cluster_id,
                subsequent_pvw_ids,
            )

        # Calculate new minimum start date
        min_start_date = execution_date + timedelta(days=min_gap_days)

        # First apply minimum-gap adjustment for all subsequent visits in this chain
        for v in linked_visits:
            if not v.from_date:
                logger.debug(
                    "update_subsequent_visits: visit_id=%s has no from_date; skipping",
                    v.id,
                )
                continue

            # We only update if the new date is later than current from_date
            if v.from_date < min_start_date:
                logger.debug(
                    "update_subsequent_visits: updating visit_id=%s from_date from %s to %s (min_gap_days=%s)",
                    v.id,
                    v.from_date,
                    min_start_date,
                    min_gap_days,
                )
                v.from_date = min_start_date
                db.add(v)
                updated_visit_ids.add(v.id)
            else:
                logger.debug(
                    "update_subsequent_visits: visit_id=%s from_date=%s already >= min_start_date=%s; no change",
                    v.id,
                    v.from_date,
                    min_start_date,
                )

        # Additional rule: for 2-visit protocols that require a June visit, when the
        # executed visit is not in June, ensure the second visit window lies fully
        # within June while keeping the largest possible interval within June.
        requires_june = bool(getattr(protocol, "requires_june_visit", False))
        is_two_visit_protocol = getattr(protocol, "visits", None) == 2

        if not (requires_june and is_two_visit_protocol and execution_date.month != 6):
            logger.debug(
                "update_subsequent_visits: June rule not applied for protocol_id=%s (requires_june=%s, visits=%s, execution_month=%s)",
                protocol.id,
                requires_june,
                getattr(protocol, "visits", None),
                execution_date.month,
            )
            continue

        # Identify the second visit for this protocol among the linked visits.
        second_visits: list[Visit] = []
        for v in linked_visits:
            if not v.from_date or not v.to_date:
                continue

            indices_for_protocol = [
                w.visit_index
                for w in v.protocol_visit_windows
                if w.protocol_id == protocol.id
            ]
            if 2 in indices_for_protocol:
                second_visits.append(v)

        if not second_visits:
            logger.debug(
                "update_subsequent_visits: no second visits found for protocol_id=%s in cluster_id=%s",
                protocol.id,
                visit.cluster_id,
            )
            continue

        # If multiple physical visits are linked as the "second" for this protocol,
        # adjust the one with the earliest from_date.
        target_visit = min(second_visits, key=lambda vv: vv.from_date)
        year = target_visit.from_date.year
        june_start = date(year, 6, 1)
        june_end = date(year, 6, 30)

        new_from = max(target_visit.from_date, june_start)
        new_to = min(target_visit.to_date, june_end)

        # Only adjust when there is a non-empty intersection with June.
        if new_from <= new_to:
            logger.debug(
                "update_subsequent_visits: June clamp for visit_id=%s from [%s, %s] to [%s, %s]",
                target_visit.id,
                target_visit.from_date,
                target_visit.to_date,
                new_from,
                new_to,
            )
            target_visit.from_date = new_from
            target_visit.to_date = new_to
            db.add(target_visit)
            updated_visit_ids.add(target_visit.id)
        else:
            logger.debug(
                "update_subsequent_visits: June clamp skipped for visit_id=%s because intersection is empty (new_from=%s, new_to=%s)",
                target_visit.id,
                new_from,
                new_to,
            )

    if updated_visit_ids:
        logger.debug(
            "update_subsequent_visits: committing updated visits %s",
            sorted(updated_visit_ids),
        )
        try:
            await db.commit()
        except Exception:
            logger.warning(
                "update_subsequent_visits: failed to commit updates for visit_ids=%s",
                sorted(updated_visit_ids),
                exc_info=True,
            )
            await db.rollback()
            raise

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    """
    Update the from_date of subsequent visits based on the executed visit's date
    and the protocol's minimum period between visits.
    """
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
    if not visit or not visit.protocol_visit_windows:
        return

    for pvw in visit.protocol_visit_windows:
        protocol = pvw.protocol
        if not protocol:
            continue

        min_gap_days = _unit_to_days(
            protocol.min_period_between_visits_value,
            protocol.min_period_between_visits_unit,
        )
        if min_gap_days <= 0:
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

        # Calculate new minimum start date
        min_start_date = execution_date + timedelta(days=min_gap_days)

        # First apply minimum-gap adjustment for all subsequent visits in this chain
        for v in linked_visits:
            if not v.from_date:
                continue

            # We only update if the new date is later than current from_date
            if v.from_date < min_start_date:
                v.from_date = min_start_date
                db.add(v)

        # Additional rule: for 2-visit protocols that require a June visit, when the
        # executed visit is not in June, ensure the second visit window lies fully
        # within June while keeping the largest possible interval within June.
        requires_june = bool(getattr(protocol, "requires_june_visit", False))
        is_two_visit_protocol = getattr(protocol, "visits", None) == 2

        if not (requires_june and is_two_visit_protocol and execution_date.month != 6):
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
            target_visit.from_date = new_from
            target_visit.to_date = new_to
            db.add(target_visit)

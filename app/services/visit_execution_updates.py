from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow

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
            selectinload(Visit.protocol_visit_windows)
            .selectinload(ProtocolVisitWindow.protocol)
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
            protocol.min_period_between_visits_unit
        )
        if min_gap_days <= 0:
            continue

        current_idx = pvw.visit_index
        
        # Find subsequent PVWs for this protocol
        subsequent_pvws_stmt = (
            select(ProtocolVisitWindow)
            .where(
                ProtocolVisitWindow.protocol_id == protocol.id,
                ProtocolVisitWindow.visit_index > current_idx
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
                Visit.cluster_id == visit.cluster_id, # Same cluster
                ProtocolVisitWindow.id.in_(subsequent_pvw_ids),
                Visit.id != visit.id # Should be redundant but safe
            )
            .options(selectinload(Visit.protocol_visit_windows))
        )
        linked_visits = (await db.execute(linked_visits_stmt)).scalars().unique().all()
        
        # Calculate new minimum start date
        min_start_date = execution_date + timedelta(days=min_gap_days)
        
        for v in linked_visits:
            # Check if this visit is actually a subsequent step for THIS protocol
            # (It is, because we filtered by subsequent_pvw_ids of this protocol)
            
            # We only update if the new date is later than current from_date
            if v.from_date < min_start_date:
                # Update from_date
                # We also need to ensure we don't push it past to_date?
                # For now, we just update from_date as requested.
                # If from_date > to_date, it might be flagged elsewhere or we should adjust to_date.
                # But usually to_date is the end of the window.
                # If we push past window, it's a scheduling conflict.
                # For now, we just set it.
                v.from_date = min_start_date
                db.add(v)

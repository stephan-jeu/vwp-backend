from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.protocol import Protocol
from app.services.visit_execution_updates import _unit_to_days
from app.schemas.visit import VisitListRow
from app.schemas.function import FunctionCompactRead
from app.schemas.species import SpeciesCompactRead
from app.schemas.user import UserNameRead


class TightVisitResponse(BaseModel):
    visit: VisitListRow
    min_start: date
    max_end: date
    slack: int
    protocol_names: list[str]


async def get_tight_visit_chains(
    db: AsyncSession, simulated_today: date | None = None
) -> list[TightVisitResponse]:
    """
    Identify 'tight' visit chains and return a flat list of unique visits
    that require attention.
    """

    # 1. Fetch relevant visits:
    stmt = (
        select(Visit)
        .join(Visit.protocol_visit_windows)
        .join(ProtocolVisitWindow.protocol)
        .join(Visit.cluster)
        .join(Visit.species)
        .options(
            selectinload(Visit.protocol_visit_windows).selectinload(
                ProtocolVisitWindow.protocol
            ),
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.species),
            selectinload(Visit.functions),
            selectinload(Visit.researchers),
        )
    )

    result = await db.execute(stmt)
    visits = result.scalars().unique().all()

    if not visits:
        return []

    # Bulk fetch logs for status derivation
    from app.models.activity_log import ActivityLog
    from app.services.visit_status_service import (
        _STATUS_ACTIONS,
        derive_visit_status,
        VisitStatusCode,
    )

    visit_ids = [v.id for v in visits]

    # Chunking to be safe with IN clause limits if necessary, but 1000s usually ok on Postgres
    log_stmt = (
        select(ActivityLog)
        .where(
            ActivityLog.target_type == "visit",
            ActivityLog.target_id.in_(visit_ids),
            ActivityLog.action.in_(_STATUS_ACTIONS),
        )
        .order_by(ActivityLog.created_at.asc())  # Process in order to finding latest
    )

    log_result = await db.execute(log_stmt)
    all_logs = log_result.scalars().all()

    # Map visit_id -> latest log
    latest_logs: dict[int, ActivityLog] = {}
    for log in all_logs:
        latest_logs[log.target_id] = log

    # Group by (cluster_id, protocol_id)
    chains: dict[tuple[int, int], list[tuple[Visit, ProtocolVisitWindow]]] = {}

    protocols_map: dict[int, Protocol] = {}

    today = simulated_today if simulated_today else date.today()

    for v in visits:
        # Filter Status (OPEN or PLANNED only)
        # Note: derive_visit_status is synchronous
        last_log = latest_logs.get(v.id)
        status_code = derive_visit_status(v, last_log, today=today)

        if status_code not in [VisitStatusCode.OPEN, VisitStatusCode.PLANNED]:
            continue

        for pvw in v.protocol_visit_windows:
            if not pvw.protocol_id:
                continue

            key = (v.cluster_id, pvw.protocol_id)
            if key not in chains:
                chains[key] = []

            chains[key].append((v, pvw))
            if pvw.protocol_id not in protocols_map and pvw.protocol:
                protocols_map[pvw.protocol_id] = pvw.protocol

    # Process Chains to find Tight Visits
    unique_tight_visits: dict[int, TightVisitResponse] = {}
    check_horizon = today - timedelta(days=8)

    for (cluster_id, protocol_id), chain_items in chains.items():
        # Sort by visit_index
        chain_items.sort(key=lambda x: x[1].visit_index)

        if not chain_items:
            continue

        protocol = protocols_map.get(protocol_id)
        if not protocol:
            continue

        # Filter: Start date of chain > (today - 8 days)
        # We assume chain starts roughly around first visit's from_date
        first_visit = chain_items[0][0]
        start_date_ref = first_visit.from_date

        is_recent_start = False
        if start_date_ref and start_date_ref > check_horizon:
            is_recent_start = True

        # Slack Calculation
        min_gap_days = _unit_to_days(
            protocol.min_period_between_visits_value,
            protocol.min_period_between_visits_unit,
        )

        es_list = []
        prev_ef = None

        # 1. Forward Pass (Earliest Start)
        for v, pvw in chain_items:
            win_start = v.from_date or date.min

            # Earliest start is at least 'today' for unexecuted visits
            es = max(win_start, today)

            if prev_ef:
                constraint_start = prev_ef + timedelta(days=min_gap_days)
                if constraint_start > es:
                    es = constraint_start

            es_list.append(es)
            prev_ef = es

        # 2. Backward Pass (Latest Start)
        ls_list = [date.max] * len(chain_items)
        next_ls = None

        for i in range(len(chain_items) - 1, -1, -1):
            v, pvw = chain_items[i]
            win_end = v.to_date or date.max

            ls = win_end
            if next_ls:
                # LS(i) <= LS(i+1) - Gap
                constraint_latest = next_ls - timedelta(days=min_gap_days)
                if constraint_latest < ls:
                    ls = constraint_latest

            ls_list[i] = ls
            next_ls = ls

        # 3. Calculate Slack & Build Result
        min_chain_slack = 999
        visit_slacks = []

        for i, (v, pvw) in enumerate(chain_items):
            es = es_list[i]
            ls = ls_list[i]

            if ls == date.max or es == date.min:
                slack = 999
            else:
                slack = (ls - es).days

            visit_slacks.append(slack)

            if slack < min_chain_slack:
                min_chain_slack = slack

        # Check filter criteria
        # 1. "min(Slack) < 14 days" AND "Recent Start"
        # 2. "visits whose to date is within 14 days from now" (and >= today)

        has_urgent_visit = False
        urgent_horizon = today + timedelta(days=14)

        for v, pvw in chain_items:
            if v.to_date and today <= v.to_date <= urgent_horizon:
                has_urgent_visit = True
                break

        is_tight_chain = (min_chain_slack < 14) and is_recent_start

        if not (is_tight_chain or has_urgent_visit):
            continue

        protocol_name = f"{protocol.species.name} - {protocol.function.name}"

        for i, (v, pvw) in enumerate(chain_items):
            slack = visit_slacks[i]
            es = es_list[i]
            ls = ls_list[i]

            # Key Logic: Deduplicate visits.
            # If visit is part of multiple Tight Chains, keep it if it's tight in at least one.
            # We want to show the worst-case slack (minimum slack) for that visit.

            if v.id in unique_tight_visits:
                existing = unique_tight_visits[v.id]
                # If this new chain offers a tighter slack for this visit, update metrics
                # Note: Logic is tricky. A visit has ONE real slack in reality? No, it depends on the constraint chain.
                # Actually, a visit is a node in multiple DAGs. We should report the most constraining one (min slack).
                if slack < existing.slack:
                    existing.slack = slack
                    existing.min_start = es
                    existing.max_end = ls

                if protocol_name not in existing.protocol_names:
                    existing.protocol_names.append(protocol_name)
            else:
                # Create new entry
                last_log = latest_logs.get(v.id)
                status_code = derive_visit_status(v, last_log, today=today)

                visit_row = VisitListRow(
                    id=v.id,
                    project_code=v.cluster.project.code,
                    project_location=v.cluster.project.location or "",
                    cluster_id=v.cluster_id,
                    cluster_number=v.cluster.cluster_number,
                    cluster_address=v.cluster.address,
                    status=status_code,
                    function_ids=[f.id for f in v.functions],
                    species_ids=[s.id for s in v.species],
                    functions=[
                        FunctionCompactRead.model_validate(f) for f in v.functions
                    ],
                    species=[SpeciesCompactRead.model_validate(s) for s in v.species],
                    researchers=[UserNameRead.model_validate(u) for u in v.researchers],
                    required_researchers=v.required_researchers,
                    visit_nr=v.visit_nr,
                    planned_week=v.planned_week,
                    from_date=v.from_date,
                    to_date=v.to_date,
                    duration=v.duration,
                    min_temperature_celsius=v.min_temperature_celsius,
                    max_wind_force_bft=v.max_wind_force_bft,
                    max_precipitation=v.max_precipitation,
                    expertise_level=v.expertise_level,
                    wbc=v.wbc,
                    fiets=v.fiets,
                    hub=v.hub,
                    dvp=v.dvp,
                    sleutel=v.sleutel,
                    remarks_planning=v.remarks_planning,
                    remarks_field=v.remarks_field,
                    priority=v.priority,
                    part_of_day=v.part_of_day,
                    advertized=v.advertized,
                    quote=v.quote,
                )

                unique_tight_visits[v.id] = TightVisitResponse(
                    visit=visit_row,
                    min_start=es,
                    max_end=ls,
                    slack=slack,
                    protocol_names=[protocol_name],
                )

    # Convert to list
    results = list(unique_tight_visits.values())

    # Sort by Slack (ascending -> most urgent first)
    results.sort(key=lambda x: x.slack)

    return results

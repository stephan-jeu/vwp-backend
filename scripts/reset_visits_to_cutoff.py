"""Reset visits to the state they were in on a cutoff date, for planner tests.

Meant for a local copy of production data (see update_habitus_db.sh). Visits
executed, not executed or cancelled before the cutoff stay as they are; every
other visit goes back to "new":

- status-bearing activity logs and the audit of the visit are removed;
- researchers, planned_week/planned_date and provisional week/lock are cleared,
  except for visits planned in the week of the cutoff (the week planning for
  the current week is already done at that moment);
- windows of follow-up visits that were moved forward by the execution of a
  reset visit (update_subsequent_visits) are widened again to the effective
  protocol window that visit generation uses. The original window is not
  stored anywhere; the start is exact for ~70% of the visits and otherwise up
  to a few weeks earlier, so restored windows are equal or slightly wider.

With the start of the season as cutoff this is a full reset.

Usage (from backend/):
    python -m scripts.reset_visits_to_cutoff --cutoff 2026-03-16            # dry run
    python -m scripts.reset_visits_to_cutoff --cutoff 2026-06-01 --apply
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from core.settings import get_settings  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402
import app.services.season_planning_service  # noqa: E402,F401  (registers all models)
from app.models.activity_log import ActivityLog  # noqa: E402
from app.models.protocol import Protocol  # noqa: E402
from app.models.protocol_visit_window import ProtocolVisitWindow  # noqa: E402
from app.models.visit import Visit  # noqa: E402
from app.models.visit_audit import VisitAudit  # noqa: E402
from app.services.visit_execution_updates import _unit_to_days  # noqa: E402
from app.services.visit_generation_common import _generate_visit_requests  # noqa: E402
from app.services.visit_status_service import _STATUS_ACTIONS  # noqa: E402

# Status logs after which a visit no longer needs planning
_DONE_ACTIONS = {
    "visit_executed",
    "visit_executed_deviation",
    "visit_executed_with_deviation",
    "visit_not_executed",
    "visit_cancelled",
}
_EXECUTED_ACTIONS = {
    "visit_executed",
    "visit_executed_deviation",
    "visit_executed_with_deviation",
}
# Non-status logs that belong to planning/executing the visit
_PLANNING_ACTIONS = {
    "visit_needs_action",
    "visit_advertised",
    "visit_advertised_cancelled",
    "visit_takeover_accepted",
}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _event_date(log: ActivityLog) -> date:
    """Date a status log refers to: the execution date when given."""
    raw = (log.details or {}).get("execution_date")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return log.created_at.date()


def _in_year(d: date, year: int) -> date:
    try:
        return d.replace(year=year)
    except ValueError:  # 29 Feb
        return date(year, 2, 28)


async def reset(cutoff: date, apply: bool) -> None:
    settings = get_settings()
    if settings.db_host not in _LOCAL_HOSTS:
        sys.exit(f"Refusing to run against non-local database host {settings.db_host!r}")

    cutoff_week = cutoff.isocalendar()
    week_monday = cutoff - timedelta(days=cutoff.weekday())
    week_sunday = week_monday + timedelta(days=6)

    async with AsyncSessionLocal() as db:
        visits = (
            (
                await db.execute(
                    select(Visit).options(
                        selectinload(Visit.researchers),
                        selectinload(Visit.protocol_visit_windows)
                        .selectinload(ProtocolVisitWindow.protocol)
                        .selectinload(Protocol.visit_windows),
                    )
                )
            )
            .scalars()
            .all()
        )
        logs = (
            (
                await db.execute(
                    select(ActivityLog).where(
                        ActivityLog.target_type == "visit",
                        ActivityLog.action.in_(_STATUS_ACTIONS | _PLANNING_ACTIONS),
                    )
                )
            )
            .scalars()
            .all()
        )
        logs_by_visit: dict[int, list[ActivityLog]] = {}
        for log in logs:
            logs_by_visit.setdefault(log.target_id, []).append(log)

        # 1. Which visits go back to "new"
        reset_ids: set[int] = set()
        exec_date_after_cutoff: dict[int, date] = {}
        for v in visits:
            visit_logs = logs_by_visit.get(v.id, [])
            done_before = any(
                log.action in _DONE_ACTIONS and _event_date(log) < cutoff
                for log in visit_logs
            )
            if done_before:
                continue
            reset_ids.add(v.id)
            for log in visit_logs:
                if log.action in _EXECUTED_ACTIONS:
                    exec_date_after_cutoff[v.id] = _event_date(log)

        def _planned_this_week(v: Visit) -> bool:
            if v.planned_date is not None:
                return week_monday <= v.planned_date <= week_sunday
            return v.planned_week == cutoff_week.week and v.from_date is not None and (
                v.from_date.year == cutoff_week.year
            )

        # 2. Windows moved forward by executions that are now undone
        effective: dict[int, tuple[date, date]] = {}
        for p in {w.protocol for v in visits for w in v.protocol_visit_windows}:
            if p is None:
                continue
            for r in _generate_visit_requests([p]):
                if r.pvw_id is not None:
                    effective[r.pvw_id] = (r.effective_window_from, r.effective_window_to)

        chain: dict[tuple[int, int], dict[int, Visit]] = {}
        for v in visits:
            for w in v.protocol_visit_windows:
                chain.setdefault((v.cluster_id, w.protocol_id), {})[w.visit_index] = v

        restored_from = restored_to = 0
        for v in visits:
            if v.id not in reset_ids or not v.from_date or not v.to_date:
                continue
            pvws = v.protocol_visit_windows
            if not pvws or any(w.id not in effective for w in pvws):
                continue
            from_shifted = to_shifted = False
            for w in pvws:
                prev = chain[(v.cluster_id, w.protocol_id)].get(w.visit_index - 1)
                executed = exec_date_after_cutoff.get(prev.id) if prev else None
                if executed is None:
                    continue
                gap = _unit_to_days(
                    w.protocol.min_period_between_visits_value,
                    w.protocol.min_period_between_visits_unit,
                )
                if gap > 0 and v.from_date == executed + timedelta(days=gap):
                    from_shifted = True
                june_end = date(v.to_date.year, 6, 30)
                if (
                    getattr(w.protocol, "requires_june_visit", False)
                    and w.visit_index == 2
                    and executed.month != 6
                    and v.to_date == june_end
                ):
                    from_shifted = to_shifted = True

            year = v.from_date.year
            if from_shifted:
                lower = max(_in_year(effective[w.id][0], year) for w in pvws)
                if lower < v.from_date:
                    v.from_date = lower
                    restored_from += 1
            if to_shifted:
                upper = min(_in_year(effective[w.id][1], year) for w in pvws)
                if upper > v.to_date:
                    v.to_date = upper
                    restored_to += 1

        # 3. Clear planning state and logs of reset visits
        kept_this_week = cleared = 0
        for v in visits:
            if v.id not in reset_ids:
                continue
            if _planned_this_week(v):
                kept_this_week += 1
                continue
            if (
                v.researchers
                or v.planned_week is not None
                or v.planned_date is not None
                or v.provisional_week is not None
                or v.provisional_locked
            ):
                cleared += 1
            v.researchers = []
            v.planned_week = None
            v.planned_date = None
            v.provisional_week = None
            v.provisional_locked = False
            v.planning_locked = False
            v.researchers_locked = False
            v.advertized = False

        reset_logs = [
            log
            for vid in reset_ids
            for log in logs_by_visit.get(vid, [])
            if _event_date(log) >= cutoff
        ]
        for log in reset_logs:
            await db.delete(log)  # also removes its activity_log_actors rows
        audits = await db.execute(
            delete(VisitAudit).where(VisitAudit.visit_id.in_(reset_ids))
        )

        print(f"Cutoff {cutoff} (week {cutoff_week.week}), {len(visits)} visits")
        print(f"  done before cutoff, kept:          {len(visits) - len(reset_ids)}")
        print(f"  reset to new:                      {len(reset_ids)}")
        print(f"    planning cleared:                {cleared}")
        print(f"    kept, planned in cutoff week:    {kept_this_week}")
        print(f"  status/planning logs removed:      {len(reset_logs)}")
        print(f"  audits removed:                    {audits.rowcount}")
        print(f"  windows restored (from / to):      {restored_from} / {restored_to}")

        if apply:
            await db.commit()
            print("Applied.")
        else:
            await db.rollback()
            print("Dry run, nothing changed. Use --apply to write.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--cutoff",
        required=True,
        type=date.fromisoformat,
        help="Simulated date (YYYY-MM-DD); use the same date as simulated today",
    )
    parser.add_argument("--apply", action="store_true", help="Write the changes")
    args = parser.parse_args()
    asyncio.run(reset(args.cutoff, args.apply))


if __name__ == "__main__":
    main()

"""Measure how much capacity a customer can lose before a shortage appears.

Removes a growing, random share of the availability (same pattern at every
step, see --seed) and reports per step:

- the minimum shortage of the bottleneck analysis (ignores the minimum period
  between visits, so it is a lower bound);
- of which committed: visits already fixed to an overbooked week;
- for the steps in --solver-at: what the season planner could not schedule
  (visits and researcher-days, plus the committed part), its solution quality
  and run time.

Everything happens in memory: the database is only read and never written.
Use the same simulated date as the cutoff of reset_visits_to_cutoff.py,
otherwise work that is already done counts as committed demand.

Usage (from backend/):
    python -m scripts.capacity_sweep --date 2026-06-15
    python -m scripts.capacity_sweep --date 2026-03-16 --limit 240 --solver-at 10,20
"""

import argparse
import asyncio
import logging
import os
import random
import re
import sys
import time
from datetime import date
from types import SimpleNamespace

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from core.settings import get_settings  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402
import app.services.season_planning_service as sps  # noqa: E402
from app.services.planning_run_errors import PlanningRunError  # noqa: E402

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_NO_AVAILABILITY = SimpleNamespace(
    morning_days=0, daytime_days=0, nighttime_days=0, flex_days=0
)
_captured: list[str] = []


class _SolverLog(logging.Handler):
    """Keeps the solver's quality summary lines."""

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "CP-SAT summary" in message or "solution rejected" in message:
            _captured.append(message)


def _days(a) -> int:
    return (
        (a.morning_days or 0)
        + (a.daytime_days or 0)
        + (a.nighttime_days or 0)
        + (a.flex_days or 0)
    )


def _percentages(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


async def sweep(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.db_host not in _LOCAL_HOSTS:
        sys.exit(f"Refusing to run against non-local database host {settings.db_host!r}")
    if args.profile_flow is not None:
        settings.constraint_profile_flow = args.profile_flow == "on"

    service = sps.SeasonPlanningService
    current_week = args.date.isocalendar().week
    steps = _percentages(args.steps)
    solver_at = set(_percentages(args.solver_at))

    solver_logger = logging.getLogger("uvicorn.error")
    solver_logger.addHandler(_SolverLog())
    solver_logger.setLevel(logging.INFO)
    for handler in solver_logger.handlers:  # keep the console quiet
        if not isinstance(handler, _SolverLog):
            handler.setLevel(logging.CRITICAL)

    async with AsyncSessionLocal() as db:
        visits = await service._load_all_active_visits(db, args.date)
        users = await service._load_all_users(db)
        base = await service._load_availability_map(db, args.date.year)
        visit_by_id = {v.id: v for v in visits}
        total = sum(_days(a) for (_, w), a in base.items() if w >= current_week)

        print(
            f"{len(visits)} visits, {len(users)} users, date {args.date} "
            f"(week {current_week}), profile flow "
            f"{'on' if settings.constraint_profile_flow else 'off'}"
        )
        print(
            f"{'removed':>8} {'left':>6} | {'analysis min':>12} {'committed':>9} | "
            "season planner (does not fit + committed = total), quality, time"
        )
        for pct in steps:
            rnd = random.Random(args.seed)
            avail = {
                key: (
                    _NO_AVAILABILITY
                    if key[1] >= current_week and rnd.random() < pct / 100
                    else value
                )
                for key, value in base.items()
            }
            left = sum(_days(a) for (_, w), a in avail.items() if w >= current_week)
            report = sps._bottleneck_analysis(args.date, visits, users, avail)
            line = (
                f"{pct:>7}% {left / total:>6.0%} | {report.total_unmet_days:>12} "
                f"{report.committed_overbooked_days:>9} |"
            )
            if pct in solver_at:
                for v in visits:
                    v.provisional_week = None
                _captured.clear()
                started = time.time()
                try:
                    diagnostics = service.solve_season(
                        args.date,
                        visits,
                        users,
                        avail,
                        timeout_seconds=args.limit,
                        num_workers=args.workers,
                    )
                    gaps = [
                        d
                        for d in diagnostics
                        if d.details.get("reason_code") == "capaciteitsgebrek"
                    ]
                    gap_days = sum(
                        int(visit_by_id[d.visit_id].required_researchers or 1)
                        for d in gaps
                    )
                    quality = re.search(
                        r"quality=(\w+) gap=([\d.]+)", " ".join(_captured)
                    )
                    line += (
                        f" {len(gaps)} visits / {gap_days} days + "
                        f"{report.committed_overbooked_days} = "
                        f"{gap_days + report.committed_overbooked_days} days, "
                        f"{quality.group(1)} ({float(quality.group(2)):.1%}), "
                        f"{time.time() - started:.0f}s"
                        if quality
                        else f" {len(gaps)} visits / {gap_days} days"
                    )
                except PlanningRunError:
                    line += f" REJECTED (WEAK and time limit), {time.time() - started:.0f}s"
            print(line, flush=True)
        await db.rollback()  # nothing was written; also drops the in-memory edits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--date",
        required=True,
        type=date.fromisoformat,
        help="Simulated date (YYYY-MM-DD); use the cutoff of the reset script",
    )
    parser.add_argument(
        "--steps",
        default="0,5,10,15,20,25,30,35,40",
        help="Percentages of availability to remove, comma separated",
    )
    parser.add_argument(
        "--solver-at",
        default="20,30,40",
        help="Steps for which the season planner is run too (slow), comma separated",
    )
    parser.add_argument("--limit", type=float, default=60, help="Solver time limit (s)")
    parser.add_argument("--workers", type=int, default=3, help="Solver workers")
    parser.add_argument("--seed", type=int, default=42, help="Seed of the removal")
    parser.add_argument(
        "--profile-flow",
        choices=["on", "off"],
        default=None,
        help="Override CONSTRAINT_PROFILE_FLOW for this run",
    )
    asyncio.run(sweep(parser.parse_args()))


if __name__ == "__main__":
    main()

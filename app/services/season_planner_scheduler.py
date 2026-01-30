from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.services.season_planning_service import SeasonPlanningService
from core.settings import get_settings
from db.session import AsyncSessionLocal

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
except ModuleNotFoundError:  # pragma: no cover
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]

_settings = get_settings()
_scheduler: AsyncIOScheduler | None = None
_job_lock = asyncio.Lock()


async def _run_season_planner_job() -> None:
    """Run the season planner once and log the result.

    The job is guarded by a lock to prevent overlapping runs if a previous
    execution has not completed yet.

    Returns:
        None.
    """

    if _job_lock.locked():
        logger.warning(
            "Season planner scheduler skipped: previous run still in progress."
        )
        return

    async with _job_lock:
        logger.info("Season planner scheduler started.")
        async with AsyncSessionLocal() as session:
            try:
                await _execute_season_planner(session)
            except Exception:
                logger.warning(
                    "Season planner scheduler failed to complete.", exc_info=True
                )
                raise


async def _execute_season_planner(session: AsyncSession) -> None:
    """Execute the seasonal planner.

    Args:
        session: Async SQLAlchemy session.

    Returns:
        None.
    """

    await SeasonPlanningService.run_season_solver(session, date.today())


def start_season_planner_scheduler() -> None:
    """Start the nightly season planner scheduler if enabled.

    Returns:
        None.
    """

    global _scheduler
    if _scheduler is not None:
        return

    if AsyncIOScheduler is None or CronTrigger is None:
        logger.info("Season planner scheduler disabled: apscheduler is not installed.")
        return

    if not _settings.season_planner_scheduler_enabled:
        logger.info("Season planner scheduler disabled by settings.")
        return

    trigger = CronTrigger.from_crontab(
        _settings.season_planner_cron,
        timezone=_settings.season_planner_timezone,
    )
    _scheduler = AsyncIOScheduler(timezone=_settings.season_planner_timezone)
    _scheduler.add_job(
        _run_season_planner_job,
        trigger=trigger,
        id="season_planner_nightly",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Season planner scheduler started (cron=%s, timezone=%s).",
        _settings.season_planner_cron,
        _settings.season_planner_timezone,
    )


def shutdown_season_planner_scheduler() -> None:
    """Shutdown the season planner scheduler if it is running.

    Returns:
        None.
    """

    global _scheduler
    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Season planner scheduler stopped.")

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.services.pvw_backfill_service import backfill_visit_protocol_visit_windows
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


async def _run_pvw_backfill_job() -> None:
    """Run the PVW backfill process once and log the result.

    The job is guarded by a lock to prevent overlapping runs if a previous
    execution has not completed yet.

    Returns:
        None.
    """

    if _job_lock.locked():
        logger.warning(
            "PVW backfill scheduler skipped: previous run still in progress."
        )
        return

    async with _job_lock:
        logger.info("PVW backfill scheduler started.")
        async with AsyncSessionLocal() as session:
            try:
                await _execute_pvw_backfill(session)
            except Exception:
                logger.warning(
                    "PVW backfill scheduler failed to complete.", exc_info=True
                )
                raise


async def _execute_pvw_backfill(session: AsyncSession) -> None:
    """Execute the PVW backfill process.

    Args:
        session: Async SQLAlchemy session.

    Returns:
        None.
    """

    await backfill_visit_protocol_visit_windows(session)


def start_pvw_backfill_scheduler() -> None:
    """Start the nightly PVW backfill scheduler if enabled.

    Returns:
        None.
    """

    global _scheduler
    if _scheduler is not None:
        return

    if AsyncIOScheduler is None or CronTrigger is None:
        logger.info("PVW backfill scheduler disabled: apscheduler is not installed.")
        return

    if not _settings.pvw_backfill_scheduler_enabled:
        logger.info("PVW backfill scheduler disabled by settings.")
        return

    trigger = CronTrigger.from_crontab(
        _settings.pvw_backfill_cron,
        timezone=_settings.pvw_backfill_timezone,
    )
    _scheduler = AsyncIOScheduler(timezone=_settings.pvw_backfill_timezone)
    _scheduler.add_job(
        _run_pvw_backfill_job,
        trigger=trigger,
        id="pvw_backfill_nightly",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "PVW backfill scheduler started (cron=%s, timezone=%s).",
        _settings.pvw_backfill_cron,
        _settings.pvw_backfill_timezone,
    )


def shutdown_pvw_backfill_scheduler() -> None:
    """Shutdown the PVW backfill scheduler if it is running.

    Returns:
        None.
    """

    global _scheduler
    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("PVW backfill scheduler stopped.")

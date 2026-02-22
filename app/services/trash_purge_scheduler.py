from __future__ import annotations

import asyncio
import traceback

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.services.admin_email_service import send_admin_alert_email
from app.services.trash_service import purge_old_trash
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


async def _run_trash_purge_job() -> None:
    """Run the trash purge once and log the result.

    The job is guarded by a lock to prevent overlapping runs if a previous
    execution has not completed yet.

    Returns:
        None.
    """

    if _job_lock.locked():
        logger.warning(
            "Trash purge scheduler skipped: previous run still in progress."
        )
        return

    async with _job_lock:
        logger.info("Trash purge scheduler started.")
        async with AsyncSessionLocal() as session:
            try:
                count = await purge_old_trash(
                    session, retention_days=_settings.trash_purge_retention_days
                )
                logger.info("Trash purge scheduler completed successfully. Purged %d items.", count)
            except Exception:
                detail = traceback.format_exc()
                try:
                    await send_admin_alert_email(
                        subject="Veldwerkplanning: prullenbak opschonen mislukt",
                        body=detail,
                    )
                except Exception:
                    logger.warning(
                        "Trash purge scheduler failed to send admin alert email.",
                        exc_info=True,
                    )
                logger.warning(
                    "Trash purge scheduler failed to complete.", exc_info=True
                )
                raise


def start_trash_purge_scheduler() -> None:
    """Start the daily trash purge scheduler if enabled.

    Returns:
        None.
    """

    global _scheduler
    if _scheduler is not None:
        return

    if AsyncIOScheduler is None or CronTrigger is None:
        logger.info("Trash purge scheduler disabled: apscheduler is not installed.")
        return

    if not _settings.trash_purge_scheduler_enabled:
        logger.info("Trash purge scheduler disabled by settings.")
        return

    trigger = CronTrigger.from_crontab(
        _settings.trash_purge_cron,
        timezone=_settings.trash_purge_timezone,
    )
    _scheduler = AsyncIOScheduler(timezone=_settings.trash_purge_timezone)
    _scheduler.add_job(
        _run_trash_purge_job,
        trigger=trigger,
        id="trash_purge_daily",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Trash purge scheduler started (cron=%s, timezone=%s, retention_days=%d).",
        _settings.trash_purge_cron,
        _settings.trash_purge_timezone,
        _settings.trash_purge_retention_days,
    )


def shutdown_trash_purge_scheduler() -> None:
    """Shutdown the trash purge scheduler if it is running.

    Returns:
        None.
    """

    global _scheduler
    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Trash purge scheduler stopped.")

from __future__ import annotations

import asyncio
import traceback
from datetime import date

from app.core.logging import logger
from app.services.admin_email_service import send_admin_alert_email
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


async def _run_holiday_reset_job() -> None:
    """Reset organization unavailabilities and seed Dutch holidays for the new year.

    Guarded by a lock to prevent overlapping runs.
    """
    if _job_lock.locked():
        logger.warning(
            "Holiday reset scheduler skipped: previous run still in progress."
        )
        return

    async with _job_lock:
        new_year = date.today().year
        logger.info("Holiday reset scheduler started for year %d.", new_year)
        async with AsyncSessionLocal() as session:
            try:
                from app.services.organization_unavailability_service import (
                    reset_and_seed_year,
                )

                seeded = await reset_and_seed_year(session, year=new_year)
                logger.info(
                    "Holiday reset scheduler completed. Seeded %d holidays for %d.",
                    len(seeded),
                    new_year,
                )
            except Exception:
                detail = traceback.format_exc()
                try:
                    await send_admin_alert_email(
                        subject="Veldwerkplanning: feestdagen reset mislukt",
                        body=detail,
                    )
                except Exception:
                    logger.warning(
                        "Holiday reset scheduler failed to send admin alert email.",
                        exc_info=True,
                    )
                logger.warning(
                    "Holiday reset scheduler failed to complete.", exc_info=True
                )
                raise


def start_holiday_reset_scheduler() -> None:
    """Start the annual holiday reset scheduler if enabled."""
    global _scheduler
    if _scheduler is not None:
        return

    if AsyncIOScheduler is None or CronTrigger is None:
        logger.info("Holiday reset scheduler disabled: apscheduler is not installed.")
        return

    if not _settings.holiday_reset_scheduler_enabled:
        logger.info("Holiday reset scheduler disabled by settings.")
        return

    # Run at 00:05 on January 1st each year
    trigger = CronTrigger(
        month=1,
        day=1,
        hour=0,
        minute=5,
        timezone=_settings.holiday_reset_timezone,
    )
    _scheduler = AsyncIOScheduler(timezone=_settings.holiday_reset_timezone)
    _scheduler.add_job(
        _run_holiday_reset_job,
        trigger=trigger,
        id="holiday_reset_annual",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Holiday reset scheduler started (runs Jan 1 at 00:05, timezone=%s).",
        _settings.holiday_reset_timezone,
    )


def shutdown_holiday_reset_scheduler() -> None:
    """Shutdown the holiday reset scheduler if running."""
    global _scheduler
    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Holiday reset scheduler stopped.")

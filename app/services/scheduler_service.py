import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.reminder_service import trigger_daily_reminder, trigger_weekly_summary
from app.services.link_validator import validate_all_links

logger = logging.getLogger("codecoach.scheduler")

scheduler: AsyncIOScheduler = None

def _run_scheduled_daily_reminder():
    """
    Sync wrapper to execute async daily reminder inside a new DB session.
    """
    logger.info("Executing scheduled daily reminder...")
    db = SessionLocal()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(trigger_daily_reminder(db))
        else:
            loop.run_until_complete(trigger_daily_reminder(db))
    except Exception as e:
        logger.error("Error running scheduled reminder: %s", e)
    finally:
        db.close()

def _run_scheduled_weekly_summary():
    logger.info("Executing scheduled weekly summary...")
    db = SessionLocal()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(trigger_weekly_summary(db))
        else:
            loop.run_until_complete(trigger_weekly_summary(db))
    except Exception as e:
        logger.error("Error running scheduled weekly summary: %s", e)
    finally:
        db.close()

def _run_scheduled_link_validation():
    logger.info("Executing scheduled link validation...")
    db = SessionLocal()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(validate_all_links(db))
        else:
            loop.run_until_complete(validate_all_links(db))
    except Exception as e:
        logger.error("Error running link validation: %s", e)
    finally:
        db.close()

def init_scheduler() -> AsyncIOScheduler:
    """
    Initializes APScheduler with a persistent SQLAlchemy jobstore.
    Survives restarts and uses misfire_grace_time so missed jobs fire upon startup.
    """
    global scheduler
    if scheduler is not None and scheduler.running:
        return scheduler

    # Use SQLite jobstore so jobs are persisted
    jobstores = {
        "default": SQLAlchemyJobStore(url=settings.effective_database_url, tablename="apscheduler_jobs")
    }

    try:
        tz = ZoneInfo(settings.TIMEZONE)
    except Exception:
        tz = ZoneInfo("UTC")

    scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=tz)

    # Register daily reminder jobs for each time in REMINDER_TIMES
    times = settings.reminder_time_list
    for idx, t_str in enumerate(times):
        try:
            parts = t_str.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            job_id = f"daily_reminder_{hour:02d}_{minute:02d}"
            # 2 hours misfire grace time so offline periods trigger catch-up
            scheduler.add_job(
                _run_scheduled_daily_reminder,
                trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
                id=job_id,
                name=f"Daily Reminder at {hour:02d}:{minute:02d}",
                replace_existing=True,
                misfire_grace_time=7200
            )
            logger.info("Configured persistent reminder job '%s' for %02d:%02d (%s)", job_id, hour, minute, settings.TIMEZONE)
        except Exception as e:
            logger.error("Failed to schedule reminder time '%s': %s", t_str, e)

    # Weekly summary: Sunday at 19:00
    scheduler.add_job(
        _run_scheduled_weekly_summary,
        trigger=CronTrigger(day_of_week="sun", hour=19, minute=0, timezone=tz),
        id="weekly_summary_job",
        name="Weekly C# Mastery Digest",
        replace_existing=True,
        misfire_grace_time=14400
    )

    # Daily link verification: 03:00 AM
    scheduler.add_job(
        _run_scheduled_link_validation,
        trigger=CronTrigger(hour=3, minute=0, timezone=tz),
        id="link_validation_job",
        name="Daily Learning Links Health Check",
        replace_existing=True,
        misfire_grace_time=7200
    )

    scheduler.start()
    logger.info("APScheduler started successfully with persistent SQLAlchemy jobstore.")
    return scheduler

def shutdown_scheduler():
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down.")


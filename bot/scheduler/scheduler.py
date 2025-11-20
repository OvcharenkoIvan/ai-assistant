# bot/scheduler/scheduler.py
from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from zoneinfo import ZoneInfo

from bot.core.config import (
    TZ,
    SYNC_INTERVAL_MINUTES,
    JOBSTORE_DB_PATH,
    BACKUP_ENABLED,
    INSTANCE_NAME,
)
from .jobs import (
    run_google_pull_and_schedule,
    send_overdue_digest,
    morning_briefing,
    health_ping,
    schedule_sqlite_backup_job,
    daily_digest_with_gpt,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{JOBSTORE_DB_PATH}")}
        _scheduler = AsyncIOScheduler(timezone=ZoneInfo(TZ), jobstores=jobstores)
    return _scheduler


def start_scheduler(app, _mem, owner_user_id: int) -> AsyncIOScheduler:
    sched = get_scheduler()

    # Google pull-sync
    sched.add_job(
        run_google_pull_and_schedule,
        trigger=IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES),
        args=[app, _mem, owner_user_id, sched],
        id="google_pull_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Утренний брифинг 08:00
    sched.add_job(
        morning_briefing,
        trigger=CronTrigger(hour=8, minute=0),
        args=[app, _mem, owner_user_id],
        id="morning_briefing",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Просрочки 20:00
    sched.add_job(
        send_overdue_digest,
        trigger=CronTrigger(hour=20, minute=0),
        args=[app, _mem, owner_user_id],
        id="overdue_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Вечерний дайджест + GPT-сводка 21:00
    sched.add_job(
        daily_digest_with_gpt,
        trigger=CronTrigger(hour=21, minute=0),
        args=[app, _mem, owner_user_id],
        id="daily_digest_with_gpt",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Health-ping
    sched.add_job(
        health_ping,
        trigger=IntervalTrigger(hours=1),
        args=[app, _mem, owner_user_id, sched],
        id="health_ping",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Бэкап (если включён)
    if BACKUP_ENABLED:
        schedule_sqlite_backup_job(sched)

    if not sched.running:
        sched.start()

    logger.info("🗓 Scheduler started for %s", INSTANCE_NAME)
    return sched

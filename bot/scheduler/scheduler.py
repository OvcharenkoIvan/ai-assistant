# bot/scheduler/scheduler.py
from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from zoneinfo import ZoneInfo

from bot.core.config import (
    TZ, SYNC_INTERVAL_MINUTES, JOBSTORE_DB_PATH,
    BACKUP_ENABLED, BACKUP_TIME, INSTANCE_NAME,
)
from .jobs import (
    run_google_pull_and_schedule,
    send_daily_digest,
    send_overdue_digest,
    health_ping,
    schedule_sqlite_backup_job,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{JOBSTORE_DB_PATH}")
        }
        _scheduler = AsyncIOScheduler(timezone=ZoneInfo(TZ), jobstores=jobstores)
    return _scheduler


def start_scheduler(app, _mem, owner_user_id: int) -> AsyncIOScheduler:
    """
    Регистрирует периодические задачи и запускает планировщик.
    - Пулл-синк Google каждые SYNC_INTERVAL_MINUTES
    - Вечерний дайджест просроченных в 20:00
    - Вечерний дайджест «план на завтра» в 21:00
    - Health ping раз в час (в лог)
    - Ночной бэкап SQLite-БД
    """
    sched = get_scheduler()

    # Pull-sync каждые N минут
    sched.add_job(
        run_google_pull_and_schedule,
        trigger=IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES),
        args=[app, _mem, owner_user_id, sched],
        id="google_pull_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Просрочки в 20:00
    sched.add_job(
        send_overdue_digest,
        trigger=CronTrigger(hour=20, minute=0),
        args=[app, _mem, owner_user_id],
        id="overdue_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # План на завтра в 21:00
    sched.add_job(
        send_daily_digest,
        trigger=CronTrigger(hour=21, minute=0),
        args=[app, _mem, owner_user_id],
        id="daily_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Health ping: раз в час — в лог (по желанию можно слать владельцу)
    sched.add_job(
        health_ping,
        trigger=IntervalTrigger(hours=1),
        args=[app, _mem, owner_user_id, sched],
        id="health_ping",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Ночной бэкап SQLite
    if BACKUP_ENABLED:
        schedule_sqlite_backup_job(sched)

    if not sched.running:
        sched.start()

    logger.info("🗓️ Scheduler started for instance=%s with jobstore=%s",
                INSTANCE_NAME, JOBSTORE_DB_PATH)
    return sched

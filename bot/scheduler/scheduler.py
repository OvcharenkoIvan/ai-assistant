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
    send_daily_digest,
    send_overdue_digest,
    morning_briefing,
    health_ping,
    schedule_sqlite_backup_job,
)
from bot.gpt.client import ask_gpt

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """
    Инициализация APScheduler без внешнего jobstore (в памяти).
    Все cron-задачи пересоздаются при старте, а напоминания
    восстанавливаются через Google pull-sync.
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=ZoneInfo(TZ))
    return _scheduler



async def build_gpt_tomorrow_summary(mem, user_id: int) -> str:
    """
    Краткая GPT-сводка по приоритетам на завтра.
    """
    try:
        tasks = mem.list_tasks(user_id=user_id, status="open", limit=50, offset=0)
    except Exception as e:
        logger.exception("GPT summary: DB error: %s", e)
        return "⚠️ Ошибка при получении задач."

    if not tasks:
        return "На завтра открытых задач нет."

    lines = [f"- {t.text} | срок: {getattr(t, 'due_at', '—')}" for t in tasks]
    messages = [
        {
            "role": "system",
            "content": (
                "Ты ассистент-планировщик. Выдели 3–5 приоритетов на завтра, "
                "не повторяя весь список. Кратко и по делу."
            ),
        },
        {"role": "user", "content": "Список задач:\n" + "\n".join(lines)},
    ]

    try:
        summary = await ask_gpt(messages)
        return summary.strip() if summary else "GPT не дал ответа."
    except Exception as e:
        logger.exception("GPT summary generation failed: %s", e)
        return "⚠️ Ошибка при построении GPT-сводки."


async def daily_digest_with_gpt(app, mem, owner_id: int) -> None:
    """
    Вечерний дайджест + GPT-сводка. Отдельная top-level функция,
    чтобы APScheduler мог её сериализовать.
    """
    try:
        await send_daily_digest(app, mem, owner_id)
        summary = await build_gpt_tomorrow_summary(mem, owner_id)
        await app.bot.send_message(
            chat_id=owner_id,
            text=f"🤖 GPT-сводка на завтра:\n{summary}",
        )
    except Exception as e:
        logger.exception("Ошибка GPT-дайджеста: %s", e)


def start_scheduler(app, _mem, owner_user_id: int) -> AsyncIOScheduler:
    """
    Регистрирует периодические задачи и запускает планировщик:
      - Пулл-синк Google каждые SYNC_INTERVAL_MINUTES
      - Утренний брифинг (08:00)
      - Вечерний дайджест просроченных (20:00)
      - Вечерний дайджест + GPT-сводка (21:00)
      - Health ping каждый час
      - Ночной бэкап SQLite-БД (если включен)
    """
    sched = get_scheduler()

    # --- Google pull-sync ---
    sched.add_job(
        run_google_pull_and_schedule,
        trigger=IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES),
        args=[app, _mem, owner_user_id, sched],
        id="google_pull_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # --- Утренний брифинг 08:00 ---
    sched.add_job(
        morning_briefing,
        trigger=CronTrigger(hour=8, minute=0),
        args=[app, _mem, owner_user_id],
        id="morning_briefing",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # --- Вечерний дайджест просроченных (20:00) ---
    sched.add_job(
        send_overdue_digest,
        trigger=CronTrigger(hour=20, minute=0),
        args=[app, _mem, owner_user_id],
        id="overdue_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # --- Вечерний дайджест + GPT-сводка (21:00) ---
    sched.add_job(
        daily_digest_with_gpt,
        trigger=CronTrigger(hour=21, minute=0),
        args=[app, _mem, owner_user_id],
        id="daily_digest_with_gpt",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # --- Health ping ---
    sched.add_job(
        health_ping,
        trigger=IntervalTrigger(hours=1),
        args=[app, _mem, owner_user_id, sched],
        id="health_ping",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # --- Ночной бэкап SQLite (если включён) ---
    if BACKUP_ENABLED:
        schedule_sqlite_backup_job(sched)

    if not sched.running:
        sched.start()

    logger.info("🗓 Scheduler started for %s", INSTANCE_NAME)
    return sched

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import OWNER_ID, INSTANCE_NAME
from bot.integrations.google_calendar import GoogleCalendarClient
from bot.scheduler.scheduler import get_scheduler

logger = logging.getLogger(__name__)


async def health_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    _mem: Any,
) -> None:
    """
    Простая команда /health для владельца бота.

    Показывает:
    - состояние БД;
    - наличие OWNER_ID;
    - статус Google Calendar;
    - количество и ближайшие задачи планировщика.
    """
    user = update.effective_user
    message = update.message

    # 1) Ограничим доступ только для владельца
    if not user or user.id != OWNER_ID:
        if message:
            await message.reply_text("Эта команда доступна только владельцу бота.")
        return

    # 2) Проверка БД
    db_status = "OK"
    try:
        # Простая проверка: попытка получить задачи владельца
        _ = _mem.list_tasks(user_id=OWNER_ID, status="open", limit=1, offset=0)
    except Exception as e:
        logger.exception("DB health check failed: %s", e)
        db_status = f"ERROR: {type(e).__name__}"

    # 3) Статус Google Calendar
    try:
        gc = GoogleCalendarClient(_mem)
        gcal_connected = gc.is_connected(OWNER_ID)
    except Exception as e:
        logger.exception("GoogleCalendarClient health check failed: %s", e)
        gcal_connected = False

    # 4) Информация о планировщике
    sched_status = "ERROR"
    jobs_info_lines = []
    try:
        sched = get_scheduler()
        jobs = sched.get_jobs()
        sched_status = f"{len(jobs)} jobs"
        for j in jobs[:8]:
            nxt = j.next_run_time.isoformat() if j.next_run_time else "—"
            jobs_info_lines.append(f"• {j.id} → {nxt}")
    except Exception as e:
        logger.exception("Scheduler health check failed: %s", e)
        jobs_info_lines.append("(ошибка чтения списка задач)")

    # 5) Сборка текста ответа
    lines = [
        f"💚 HEALTH [{INSTANCE_NAME}]",
        "",
        f"DB: {db_status}",
        f"Owner ID: {OWNER_ID if OWNER_ID else 'NOT SET'}",
        f"Google Calendar: {'connected' if gcal_connected else 'not configured'}",
        f"Scheduler: {sched_status}",
    ]

    if jobs_info_lines:
        lines.append("")
        lines.append("Ближайшие задачи планировщика:")
        lines.extend(jobs_info_lines)

    text = "\n".join(lines)

    if message:
        await message.reply_text(text)

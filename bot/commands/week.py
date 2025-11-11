# bot/commands/week.py
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import TZ
from bot.commands.task_actions import build_task_actions_kb

logger = logging.getLogger(__name__)


def _fmt_date(epoch: int) -> str:
    """YYYY-MM-DD в локальной TZ"""
    tz = ZoneInfo(TZ)
    return datetime.fromtimestamp(epoch, tz=tz).strftime("%Y-%m-%d")


def _fmt_time(epoch: Optional[int]) -> str:
    if not epoch:
        return "—"
    try:
        dt = datetime.fromtimestamp(int(epoch), tz=ZoneInfo(TZ))
        return dt.strftime("%H:%M")
    except Exception:
        return "—"


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    /week — обзор задач на ближайшие 7 дней (status='open', due_at в пределах 7 суток).
    Группировка по дате. Под каждой задачей — стандартные кнопки из task_actions.
    """
    if not update.message:
        return

    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    tz = ZoneInfo(TZ)
    now = datetime.now(tz)
    start_ts = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    end_ts = int((now + timedelta(days=7)).timestamp())

    try:
        tasks: List = _mem.list_upcoming_tasks(
            user_id=user.id,
            due_from=start_ts,
            due_to=end_ts,
            status="open",
            limit=500,
        )
    except Exception as e:
        logger.exception("week_command: DB error: %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось получить задачи на неделю.")
        return

    if not tasks:
        await update.message.reply_text("📭 На ближайшие 7 дней задач нет. Добавь через /task …")
        return

    # группируем по дате (локальной)
    grouped: Dict[str, List[Any]] = {}
    for t in tasks:
        due = getattr(t, "due_at", None)
        date_key = _fmt_date(due) if due else "Без даты"
        grouped.setdefault(date_key, []).append(t)

    # сортировка по дате
    sorted_days = sorted(grouped.keys())
    header = f"📅 Задачи на неделю ({len(tasks)}):"
    await update.message.reply_text(header)

    for day in sorted_days:
        await update.message.reply_text(f"📆 {day} ({len(grouped[day])})")

        for t in grouped[day]:
            task_id = getattr(t, "id", None)
            if task_id is None:
                continue

            time_str = _fmt_time(getattr(t, "due_at", None))
            title = getattr(t, "text", "")
            caption = f"🕒 {time_str} — {title}\n[id: {task_id}]"

            try:
                await update.message.reply_text(
                    caption,
                    reply_markup=build_task_actions_kb(task_id),
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning("week_command: failed to send task id=%s: %s", task_id, e)

# bot/commands/today.py
from __future__ import annotations

import logging
import asyncio
from typing import List, Optional, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import TZ
from bot.commands.task_actions import build_task_actions_kb

logger = logging.getLogger(__name__)


async def _run_blocking(func, *args, **kwargs):
    """Запуск синхронной функции в thread pool (как в tasks.py)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _fmt_time(epoch: Optional[int]) -> str:
    if not epoch:
        return "—"
    try:
        dt = datetime.fromtimestamp(int(epoch), tz=ZoneInfo(TZ))
        return dt.strftime("%H:%M")
    except Exception:
        return "—"


def _today_bounds() -> tuple[int, int]:
    """Начало и конец текущих суток в локальной TZ."""
    tz = ZoneInfo(TZ)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    /today — показать задачи на сегодня (status='open' и дедлайн в текущие сутки).
    Под каждой задачей — универсальная клавиатура из task_actions:
      - 🔁 На завтра
      - 🕒 Другое время
      - ✅ Выполнено
      - ❌ Удалить
    """
    if not update.message:
        return

    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    start_ts, end_ts = _today_bounds()

    try:
        tasks: List = await _run_blocking(
            _mem.list_upcoming_tasks,
            user_id=user.id,
            due_from=start_ts,
            due_to=end_ts,
            status="open",
            limit=200,
        )
    except Exception as e:
        logger.exception("today_command: DB error: %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось получить задачи на сегодня.")
        return

    if not tasks:
        await update.message.reply_text("На сегодня задач с дедлайном нет. Добавь через /task …")
        return

    # шапка
    await update.message.reply_text(
        f"🗓 Задачи на сегодня ({len(tasks)}):\n"
        f"(используй кнопки под каждой карточкой)"
    )

    # карточки с кнопками
    for t in tasks:
        task_id = getattr(t, "id", None)
        if task_id is None:
            logger.warning("today_command: пропущена задача без id: %r", t)
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
            logger.warning("today_command: failed to send task id=%s: %s", task_id, e)
            continue

# bot/commands/task_actions.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

from bot.core.config import TZ

logger = logging.getLogger(__name__)


# ---------- общие утилиты ----------

async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def build_task_actions_kb(task_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки для просроченной/актуальной задачи.
    callback_data формат: task_action:<task_id>:<action>
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 На завтра", callback_data=f"task_action:{task_id}:move_tomorrow"),
            InlineKeyboardButton("🕒 Другое время", callback_data=f"task_action:{task_id}:reschedule"),
        ],
        [
            InlineKeyboardButton("✅ Выполнено", callback_data=f"task_action:{task_id}:mark_done"),
            InlineKeyboardButton("❌ Удалить", callback_data=f"task_action:{task_id}:delete"),
        ]
    ])


# ---------- обработчик callback-кнопок ----------

async def handle_task_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    Обрабатывает task_action:<task_id>:<action>.
    """
    cq = update.callback_query
    if not cq or not cq.data or not cq.data.startswith("task_action:"):
        return

    try:
        _, task_id_str, action = cq.data.split(":", 2)
        task_id = int(task_id_str)
    except Exception:
        await cq.answer("Некорректное действие", show_alert=True)
        return

    user = update.effective_user
    if not user:
        await cq.answer("Неизвестный пользователь", show_alert=True)
        return

    # Получаем задачу
    task = await _run_blocking(_mem.get_task, task_id)
    if not task or task.user_id != user.id:
        await cq.answer("Задача не найдена", show_alert=True)
        return

    # --- действия ---
    if action == "move_tomorrow":
        new_due = int((task.due_at or datetime.now().timestamp()) + 86400)
        ok = await _run_blocking(_mem.update_task, task.id, due_at=new_due)
        if ok:
            await cq.edit_message_text(f"🔁 Перенесено на завтра: [{task.id}] {task.text}")
        else:
            await cq.answer("Не удалось перенести", show_alert=True)

    elif action == "mark_done":
        # 1) статус
        ok = await _run_blocking(_mem.update_task, task.id, status="done")
        # 2) префикс «✅ »
        if ok:
            title = task.text
            if not title.startswith("✅ "):
                title = "✅ " + title
                await _run_blocking(_mem.update_task, task.id, text=title)
            await cq.edit_message_text(f"✅ Выполнено: [{task.id}] {title}")
        else:
            await cq.answer("Не удалось завершить", show_alert=True)

    elif action == "delete":
        ok = await _run_blocking(_mem.delete_task, task.id)
        if ok:
            await cq.edit_message_text(f"🗑 Удалено: [{task.id}] {task.text}")
        else:
            await cq.answer("Не удалось удалить", show_alert=True)

    elif action == "reschedule":
        # ставим «ожидание» новой даты/времени от пользователя
        context.user_data["reschedule_task_id"] = task.id
        await cq.answer()
        if cq.message:
            await cq.message.reply_text("🕒 Введите новую дату/время (например: «завтра 10:30», «в пятницу 15:00», «через 2 часа»).")
    else:
        await cq.answer("Неизвестное действие", show_alert=True)


# ---------- обработчик текстового ввода новой даты/времени ----------

async def handle_reschedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> bool:
    """
    Если у пользователя установлен user_data['reschedule_task_id'], пытается распарсить введённый текст
    и переназначить due_at. Возвращает True, если сообщение обработано (чтобы main мог пропустить GPT/intent).
    """
    if not update.message or not update.message.text:
        return False

    task_id = context.user_data.get("reschedule_task_id")
    if not task_id:
        return False  # не наш кейс

    text = update.message.text.strip()
    tz = ZoneInfo(TZ)
    settings = {
        "TIMEZONE": TZ,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": datetime.now(tz),
        "PARSERS": ["relative-time", "absolute-time", "timestamp", "custom-formats"],
        "SKIP_TOKENS": ["в", "около", "к", "на"],
    }
    dt = dateparser.parse(text, settings=settings)

    if not dt:
        await update.message.reply_text("Не смог понять дату. Попробуйте ещё раз, например: «завтра 09:30» или «через 2 часа».")
        return True

    new_due = int(dt.timestamp())
    ok = await _run_blocking(_mem.update_task, int(task_id), due_at=new_due)
    if ok:
        when = datetime.fromtimestamp(new_due, tz=tz).strftime("%Y-%m-%d %H:%M")
        await update.message.reply_text(f"🗓 Переназначено на: {when}")
        # сбрасываем ожидание
        context.user_data.pop("reschedule_task_id", None)
    else:
        await update.message.reply_text("❌ Не удалось перенести. Попробуйте ещё раз.")

    return True

from __future__ import annotations

import logging
import asyncio
import re
from typing import Optional, Any, List
from datetime import datetime
from zoneinfo import ZoneInfo

import dateparser
from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import TZ
from bot.integrations.google_calendar import GoogleCalendarClient
from bot.commands.task_actions import build_task_actions_kb

logger = logging.getLogger(__name__)


# ---------------------------
# Helpers
# ---------------------------

async def _run_blocking(func, *args, **kwargs):
    """Run sync function in executor to avoid blocking PTB event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _fmt_epoch(due_at: Optional[int]) -> str:
    if not due_at:
        return "—"
    try:
        return datetime.fromtimestamp(int(due_at), tz=ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(due_at)


def _parse_due_at_and_flags(text: str) -> tuple[Optional[int], dict]:
    """
    Parse natural language date/time. Returns (epoch or None, extra_flags).
    Marks all_day if no explicit time or triggers (e.g., 'весь день', 'день рождения', 'др').
    """
    tzinfo = ZoneInfo(TZ)
    settings = {
        "TIMEZONE": TZ,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": datetime.now(tzinfo),
        "PARSERS": ["relative-time", "absolute-time", "timestamp", "custom-formats"],
        "SKIP_TOKENS": ["в", "около", "к", "на"],
    }

    dt = dateparser.parse(text, settings=settings)
    extra_flags: dict = {}
    if not dt:
        return None, extra_flags

    all_day_triggers = bool(
        re.search(r"\b(весь день|целый день|день рождения|др|birthday)\b", text, re.IGNORECASE)
    )
    time_explicit = bool(
        re.search(r"\b([01]?\d|2[0-3])[:.]\d{2}\b", text)
    ) or bool(
        re.search(r"\bв\s*([01]?\d|2[0-3])\s*час", text, re.IGNORECASE)
    )

    epoch = int(dt.timestamp())
    if all_day_triggers or (dt.hour == 0 and dt.minute == 0 and not time_explicit):
        extra_flags["all_day"] = True

    return epoch, extra_flags


# ---------------------------
# /task — добавить задачу
# ---------------------------

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    /task <текст> — добавляет задачу. Пытается распознать дату/время.
    Если есть due_at и подключён Google — создаёт событие в календаре.
    После создания показывает карточку задачи с inline-кнопками действий.
    """
    if not update.message:
        return

    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    raw = (update.message.text or "").strip()
    # срезаем саму команду
    if raw.startswith("/task"):
        raw = raw[len("/task"):].strip()

    if not raw:
        await update.message.reply_text(
            "Укажи текст задачи, например:\n"
            "/task Встреча с Петром завтра в 15:00"
        )
        return

    due_at, flags = _parse_due_at_and_flags(raw)
    extra = {"source": "cmd:/task"}
    extra.update(flags)

    # 1) локально
    try:
        task_id = await _run_blocking(
            _mem.add_task,
            user_id=user.id,
            text=raw,
            raw_text=raw,
            due_at=due_at,
            extra=extra,
        )
        logger.info("Task via /task: id=%s user_id=%s due_at=%s", task_id, user.id, due_at)
    except Exception as e:
        logger.exception("add_task_command: DB error: %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось сохранить задачу.")
        return

    # 2) Google Calendar (если есть due_at)
    created_in_calendar = False
    task_obj = None
    try:
        task_obj = await _run_blocking(_mem.get_task, task_id)
        if due_at and task_obj:
            gc = GoogleCalendarClient(_mem)
            if gc.is_connected(user.id):
                await _run_blocking(gc.create_event, user.id, task_obj)
                created_in_calendar = True
    except Exception as e:
        logger.warning("add_task_command: failed Google event create, task_id=%s: %s", task_id, e)

    suffix = ""
    if due_at:
        suffix += f" (срок: {_fmt_epoch(due_at)})"
    if created_in_calendar:
        suffix += " • 📅 добавлено в Google Calendar"

    await update.message.reply_text(f"✅ Задача сохранена (id={task_id}){suffix}")

    # 3) Карточка задачи с inline-кнопками
    try:
        if not task_obj:
            task_obj = await _run_blocking(_mem.get_task, task_id)
        if task_obj:
            mark = "🕒" if task_obj.due_at else "•"
            cal = " 📅" if getattr(task_obj, "calendar_event_id", None) else ""
            text = (
                f"{mark} [{task_obj.id}] {task_obj.text}{cal}\n"
                f"Срок: {_fmt_epoch(task_obj.due_at)}"
            )
            kb = build_task_actions_kb(task_obj.id)
            await update.message.reply_text(text, reply_markup=kb)
    except Exception:
        logger.warning("add_task_command: failed to send task card with actions", exc_info=True)


# ---------------------------
# /tasks — список задач
# ---------------------------

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    Показывает список открытых задач.
    Для каждой задачи отправляет отдельное сообщение с inline-кнопками действий.
    """
    if not update.message:
        return
    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    try:
        items = await _run_blocking(_mem.list_tasks, user_id=user.id, status="open", limit=50, offset=0)
    except Exception as e:
        logger.exception("tasks: DB error: %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось получить список задач.")
        return

    if not items:
        await update.message.reply_text("📭 Нет открытых задач.")
        return

    await update.message.reply_text("📝 Твои задачи (можно управлять кнопками ниже):")

    for t in items:
        try:
            mark = "🕒" if t.due_at else "•"
            cal = " 📅" if getattr(t, "calendar_event_id", None) else ""
            text = f"{mark} [{t.id}] {t.text}{cal}\nСрок: {_fmt_epoch(t.due_at)}"
            kb = build_task_actions_kb(t.id)
            await update.message.reply_text(text, reply_markup=kb)
        except Exception:
            logger.warning("tasks: failed to send task card for id=%s", t.id, exc_info=True)


# ---------------------------
# /reset_tasks — удалить ВСЕ задачи (и связанные Google-события)
# ---------------------------

async def reset_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    Удаляет все задачи пользователя.
    Перед удалением — если подключён Google — удаляем связанные события в календаре.
    """
    if not update.message:
        return
    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    try:
        items = await _run_blocking(_mem.list_tasks, user_id=user.id, status=None, limit=1000, offset=0)
    except Exception as e:
        logger.exception("reset_tasks: DB error (list): %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось получить список задач.")
        return

    # Проверяем подключение Google
    try:
        gc = GoogleCalendarClient(_mem)
        is_connected = gc.is_connected(user.id)
    except Exception:
        is_connected = False

    deleted_count = 0

    if items:
        for t in items:
            # если есть связь с событием — удаляем его
            if is_connected and getattr(t, "calendar_event_id", None):
                try:
                    await _run_blocking(gc.delete_event, user.id, t)
                except Exception as e:
                    logger.warning("reset_tasks: failed Google event delete for task_id=%s: %s", t.id, e)
            # удаляем локальную запись
            try:
                ok = await _run_blocking(_mem.delete_task, t.id)
                if ok:
                    deleted_count += 1
            except Exception as e:
                logger.warning("reset_tasks: failed local delete task id=%s: %s", t.id, e)

    await update.message.reply_text(f"🗑 Удалено задач: {deleted_count}")


# ---------------------------
# /complete — отметить задачу выполненной и пометить в календаре
# ---------------------------

async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem: Any) -> None:
    """
    /complete <номер_в_списке> — отмечает задачу как выполненную (status=done)
    И дополнительно префиксует название задачки «✅ ...».
    """
    if not update.message:
        return

    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Укажи номер задачи: /complete <номер>")
        return

    try:
        idx = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Номер задачи должен быть числом.")
        return

    try:
        items = await _run_blocking(_mem.list_tasks, user_id=user.id, status="open", limit=200, offset=0)
    except Exception as e:
        logger.exception("complete_task: DB error (list): %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось получить список задач.")
        return

    if idx < 1 or idx > len(items):
        await update.message.reply_text("⚠️ Неверный номер задачи.")
        return

    task = items[idx - 1]

    # 1) статус done
    try:
        ok = await _run_blocking(_mem.update_task, task.id, status="done")
        if not ok:
            await update.message.reply_text("⚠️ Не удалось обновить задачу.")
            return
    except Exception as e:
        logger.exception("complete_task: DB error (update status): %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось обновить задачу.")
        return

    # 2) префикс «✅ » в названии (без двойного префикса)
    try:
        prefixed = task.text
        if not prefixed.startswith("✅ "):
            prefixed = f"✅ {prefixed}"
        await _run_blocking(_mem.update_task, task.id, text=prefixed)
    except Exception as e:
        # не критично — задача уже закрыта; просто лог
        logger.warning("complete_task: failed to prefix checkmark for task_id=%s: %s", task.id, e)

    await update.message.reply_text(f"✅ Задача '{task.text}' отмечена как выполненная.")
    
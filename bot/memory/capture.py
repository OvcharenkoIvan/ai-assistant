# bot/memory/capture.py
"""
Smart Capture: сохранение текста пользователя как задачи или заметки через inline-кнопки.
Полностью совместимо с python-telegram-bot v20 и асинхронной архитектурой.

Особенности:
- Интеграция с formatters.py (email, meeting, vector)
- Сохраняются raw_text и extra_data (результат GPT)
- TTL для capture_store: неактивные captures автоматически очищаются каждый день в 00:00
"""

from __future__ import annotations

import logging
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Tuple
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes, Application

from bot.memory.memory_loader import get_memory
from bot.memory.formatters import format_text  # интеграция форматеров

logger = logging.getLogger(__name__)

# Singleton memory backend
_mem = get_memory()

# capture_store: capture_id -> (text, timestamp)
capture_store: Dict[str, Tuple[str, datetime]] = {}

# TTL настроен на 7 дней для временного хранилища
CAPTURE_TTL = timedelta(days=7)

# Константы действий
TASK = "task"
NOTE = "note"
CANCEL = "cancel"


def build_capture_keyboard(capture_id: str) -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру для Smart Capture."""
    buttons = [
        [
            InlineKeyboardButton("✅ Задача", callback_data=f"capture:{TASK}:{capture_id}"),
            InlineKeyboardButton("📝 Заметка", callback_data=f"capture:{NOTE}:{capture_id}")
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"capture:{CANCEL}:{capture_id}")]
    ]
    return InlineKeyboardMarkup(buttons)


async def offer_capture(source, context=None):
    """
    Показывает пользователю inline-кнопки для сохранения текста.
    source: Update или Message (Telegram)
    context: ContextTypes.DEFAULT_TYPE (опционально)
    """
    # Если передан Update
    if hasattr(source, "message"):
        message = source.message
    else:  # Если передан Message напрямую
        message = source

    if not message or not message.text:
        return

    import uuid
    from datetime import datetime

    capture_id = str(uuid.uuid4())
    capture_store[capture_id] = (message.text, datetime.now())

    kb = build_capture_keyboard(capture_id)
    preview = message.text if len(message.text) <= 50 else message.text[:47] + "..."
    await message.reply_text(
        f"Хотите сохранить это?\n\n<code>{preview}</code>",
        reply_markup=kb,
        parse_mode="HTML",
    )


async def _run_blocking(func, *args, **kwargs):
    """Запуск синхронной функции в отдельном executor-е для неблокирования event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def handle_capture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатия inline-кнопок Smart Capture.
    Применяет format_text перед сохранением в базу.
    """
    callback = update.callback_query
    if not callback or not callback.data or not callback.data.startswith("capture:"):
        return

    capture_id = None
    try:
        # Разбор callback_data
        _, kind, capture_id = callback.data.split(":", 2)
        entry = capture_store.pop(capture_id, None)
        raw_text = entry[0] if entry else None
        user_id = callback.from_user.id if callback.from_user else None

        if not raw_text:
            await callback.answer("⚠️ Истекло время сохранения", show_alert=True)
            return

        # Применяем форматеры (GPT + fallback)
        try:
            fmt_result = await format_text(raw_text, fmt_type=kind, user_id=user_id)
        except Exception as e:
            logger.warning("Formatter failed, fallback to raw_text: %s", e)
            fmt_result = {"body": raw_text, "raw_text": raw_text}

        # Сохраняем в memory с raw_text и extra_data
        if kind == TASK:
            task_id = await _run_blocking(
                _mem.add_task,
                text=fmt_result.get("body"),
                user_id=user_id,
                raw_text=fmt_result.get("raw_text"),
                extra_data=fmt_result
            )
            reply_text = f"✅ Задача сохранена (id={task_id})"
            logger.info("Task saved id=%s user_id=%s", task_id, user_id)

        elif kind == NOTE:
            note_id = await _run_blocking(
                _mem.add_note,
                text=fmt_result.get("body"),
                user_id=user_id,
                raw_text=fmt_result.get("raw_text"),
                extra_data=fmt_result
            )
            reply_text = f"📝 Заметка сохранена (id={note_id})"
            logger.info("Note saved id=%s user_id=%s", note_id, user_id)

        elif kind == CANCEL:
            reply_text = "❌ Отменено."
            logger.info("Capture cancelled by user_id=%s", user_id)

        else:
            reply_text = "❌ Неизвестное действие."
            logger.warning("Unknown capture action: %s", kind)

        if callback.message:
            await callback.message.edit_text(reply_text)
        await callback.answer()

    except Exception as e:
        logger.exception("handle_capture_callback error: %s", e)
        try:
            await callback.answer("Ошибка при сохранении", show_alert=True)
        except Exception:
            pass

    finally:
        if capture_id:
            capture_store.pop(capture_id, None)


async def cleanup_expired_captures():
    """Удаляет из capture_store записи старше CAPTURE_TTL и логирует их."""
    now = datetime.now()
    expired = [cid for cid, (_, ts) in capture_store.items() if now - ts > CAPTURE_TTL]
    for cid in expired:
        text, _ = capture_store.pop(cid)
        logger.info("Expired capture removed: %s -> %s", cid, text[:50])


async def schedule_daily_cleanup(app: Application):
    """Запуск очистки capture_store каждый день в 00:00."""
    async def _daily_task():
        while True:
            now = datetime.now()
            next_run = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            wait_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            await cleanup_expired_captures()

    app.create_task(_daily_task())

# bot/memory/capture.py
"""
Smart Capture: сохранение текста пользователя как задачи или заметки через inline-кнопки.
Полностью совместимо с python-telegram-bot v20 и асинхронной архитектурой.
"""

from __future__ import annotations

import logging
import uuid
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

from bot.memory.memory_loader import get_memory

logger = logging.getLogger(__name__)

# Singleton memory backend
_mem = get_memory()

# Временное хранилище сообщений (capture_id -> текст)
capture_store: dict[str, str] = {}

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


async def offer_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает пользователю inline-кнопки для сохранения текста.
    Используется при низко- или высокоуверенной классификации intent.
    """
    message = update.effective_message
    if not message or not message.text:
        return

    capture_id = str(uuid.uuid4())
    capture_store[capture_id] = message.text

    kb = build_capture_keyboard(capture_id)
    preview = message.text if len(message.text) <= 50 else message.text[:47] + "..."
    await message.reply_text(
        f"Хотите сохранить это?\n\n<code>{preview}</code>",
        reply_markup=kb,
        parse_mode="HTML",
    )


async def _run_blocking(func, *args, **kwargs):
    """Запуск синхронной функции в отдельном executor-е для не блокирования event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def handle_capture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатия inline-кнопок Smart Capture."""
    callback = update.callback_query
    if not callback or not callback.data or not callback.data.startswith("capture:"):
        return

    try:
        _, kind, capture_id = callback.data.split(":", 2)
        text = capture_store.pop(capture_id, None)
        user_id = callback.from_user.id if callback.from_user else None

        if not text:
            await callback.answer("⚠️ Истекло время сохранения", show_alert=True)
            return

        if kind == TASK:
            task_id = await _run_blocking(_mem.add_task, text=text, user_id=user_id)
            reply_text = f"✅ Задача сохранена (id={task_id})"
            logger.info("Task saved id=%s user_id=%s", task_id, user_id)

        elif kind == NOTE:
            note_id = await _run_blocking(_mem.add_note, text=text, user_id=user_id)
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
            pass  # безопасно игнорируем

    finally:
        # Очистка устаревших записей (если вдруг остались)
        capture_store.pop(capture_id, None)

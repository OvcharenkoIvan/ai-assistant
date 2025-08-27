# bot/memory/capture.py
"""
Smart Capture: модуль для сохранения текста пользователя
как задачи или заметки через inline-кнопки.

Использует единый backend через memory_loader.get_memory().
Асинхронные операции выполняются через executor для синхронных backend-методов.
"""

from __future__ import annotations

import logging
import uuid
import asyncio
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.memory.memory_loader import get_memory

logger = logging.getLogger(__name__)

# Singleton memory backend
_mem = get_memory()

# Временное хранилище сообщений для capture (id → текст)
capture_store: dict[str, str] = {}

# Константы действий
TASK = "task"
NOTE = "note"
CANCEL = "cancel"


def build_capture_keyboard(capture_id: str) -> types.InlineKeyboardMarkup:
    """Строит inline-клавиатуру для Smart Capture."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Задача", callback_data=f"capture:{TASK}:{capture_id}")
    builder.button(text="📝 Заметка", callback_data=f"capture:{NOTE}:{capture_id}")
    builder.button(text="❌ Отмена", callback_data=f"capture:{CANCEL}:{capture_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


async def offer_capture(message: types.Message) -> None:
    """Показывает пользователю inline-кнопки для сохранения его текста."""
    if not message.text:
        return

    capture_id = str(uuid.uuid4())
    capture_store[capture_id] = message.text

    kb = build_capture_keyboard(capture_id)
    preview = message.text if len(message.text) <= 50 else message.text[:47] + "..."
    await message.answer(
        f"Хотите сохранить это?\n\n<code>{preview}</code>",
        reply_markup=kb,
        parse_mode="HTML",
    )


async def _run_blocking(func, *args, **kwargs):
    """Запуск синхронной функции в executor-е."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    except Exception as e:
        logger.exception("Error in blocking call %s: %s", func.__name__, e)
        raise


async def handle_capture_callback(callback: types.CallbackQuery) -> None:
    """Обработчик нажатия inline-кнопок."""
    try:
        data = callback.data
        if not data or not data.startswith("capture:"):
            return

        _, kind, capture_id = data.split(":", 2)
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

        if callback.message:
            await callback.message.edit_text(reply_text)
        await callback.answer()

    except Exception as e:
        logger.exception("handle_capture_callback error: %s", e)
        try:
            await callback.answer("Ошибка при сохранении", show_alert=True)
        except Exception:
            pass  # безопасно игнорируем, если callback.message уже удалено

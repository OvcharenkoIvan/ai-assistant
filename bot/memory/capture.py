# bot/memory/capture.py
"""
Smart Capture: модуль для сохранения текста пользователя
как задачи или заметки через inline-кнопки.

Использует SQLite-хранилище (memory_sqlite.py).
"""

from __future__ import annotations

import logging
import uuid
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.memory.memory_sqlite import add_task, add_note

logger = logging.getLogger(__name__)

# Временное хранилище сообщений для capture (id → текст)
capture_store: dict[str, str] = {}


def build_capture_keyboard(capture_id: str) -> types.InlineKeyboardMarkup:
    """
    Строит inline-клавиатуру для Smart Capture.
    capture_id — ключ в capture_store.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Задача", callback_data=f"capture:task:{capture_id}")
    builder.button(text="📝 Заметка", callback_data=f"capture:note:{capture_id}")
    builder.button(text="❌ Отмена", callback_data=f"capture:cancel:{capture_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


async def offer_capture(message: types.Message) -> None:
    """
    Показывает пользователю inline-кнопки для сохранения его текста.
    Обычно вызывается из intent-обработчика (intent.py).
    """
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


async def handle_capture_callback(callback: types.CallbackQuery) -> None:
    """
    Обработчик нажатия inline-кнопок.
    Сохраняет текст как задачу или заметку.
    """
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

        if kind == "task":
            task_id = add_task(text=text, user_id=user_id)
            reply_text = f"✅ Задача сохранена (id={task_id})"
            logger.info("Task saved id=%s user_id=%s", task_id, user_id)

        elif kind == "note":
            note_id = add_note(text=text, user_id=user_id)
            reply_text = f"📝 Заметка сохранена (id={note_id})"
            logger.info("Note saved id=%s user_id=%s", note_id, user_id)

        elif kind == "cancel":
            reply_text = "❌ Отменено."
            logger.info("Capture cancelled by user_id=%s", user_id)

        else:
            reply_text = "❌ Неизвестное действие."

        # Обновляем сообщение с кнопками
        await callback.message.edit_text(reply_text)
        await callback.answer()

    except Exception as e:
        logger.exception("handle_capture_callback error: %s", e)
        await callback.answer("Ошибка при сохранении", show_alert=True)

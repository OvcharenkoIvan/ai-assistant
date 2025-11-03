# bot/memory/capture.py
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

from bot.memory.formatters import format_text  # GPT + fallback
from bot.memory.memory_loader import get_memory

logger = logging.getLogger(__name__)

# capture_id -> (text, timestamp)
capture_store: Dict[str, Tuple[str, datetime]] = {}

CAPTURE_TTL = timedelta(days=7)

TASK = "task"
NOTE = "note"
CANCEL = "cancel"

def _kb(capture_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Задача", callback_data=f"capture:{TASK}:{capture_id}"),
            InlineKeyboardButton("📝 Заметка", callback_data=f"capture:{NOTE}:{capture_id}"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"capture:{CANCEL}:{capture_id}")],
    ])

async def offer_capture(source, context: Optional[ContextTypes.DEFAULT_TYPE] = None):
    """
    Показывает пользователю inline-кнопки для сохранения текста (Smart Capture).
    source: Message или Update.message
    """
    message = getattr(source, "message", None) or source
    if not message or not getattr(message, "text", None):
        return

    cid = str(uuid.uuid4())
    capture_store[cid] = (message.text, datetime.now())

    preview = message.text if len(message.text) <= 50 else (message.text[:47] + "...")
    await message.reply_text(
        f"Хотите сохранить это?\n\n<code>{preview}</code>",
        reply_markup=_kb(cid),
        parse_mode="HTML",
    )

async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

async def handle_capture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатий на кнопки Smart Capture.
    callback_data: capture:<task|note|cancel>:<capture_id>
    """
    cq = update.callback_query
    if not cq or not cq.data or not cq.data.startswith("capture:"):
        return

    try:
        _, kind, cid = cq.data.split(":", 2)
    except Exception:
        await cq.answer("Некорректное действие", show_alert=True)
        return

    entry = capture_store.pop(cid, None)
    raw_text = entry[0] if entry else None
    user_id = cq.from_user.id if cq.from_user else None

    if not raw_text:
        await cq.answer("⚠️ Истекло время сохранения", show_alert=True)
        return

    if kind == CANCEL:
        await cq.edit_text("❌ Отменено.")
        await cq.answer()
        return

    # Инициализация памяти лениво, чтобы не ловить циклы импортов
    _mem = get_memory()

    # Нормализуем текст через форматтер (GPT + fallback)
    try:
        fmt = await format_text(raw_text, fmt_type=kind, user_id=user_id)
    except Exception as e:
        logger.warning("format_text failed, fallback to raw: %s", e)
        fmt = {"body": raw_text, "raw_text": raw_text}

    body = (fmt.get("body") or raw_text).strip()
    due_at = fmt.get("due_at")
    extra = dict(fmt)
    extra["source"] = "smart_capture"

    try:
        if kind == TASK:
            new_id = await _run_blocking(
                _mem.add_task,
                user_id=user_id or 0,
                text=body,
                raw_text=raw_text,
                due_at=due_at,
                extra=extra,
            )
            await cq.edit_text(f"✅ Задача сохранена (id={new_id})")
            logger.info("Capture→Task saved id=%s user_id=%s due_at=%s", new_id, user_id, due_at)

        elif kind == NOTE:
            new_id = await _run_blocking(
                _mem.add_note,
                user_id=user_id or 0,
                text=body,
                raw_text=raw_text,
                extra=extra,
            )
            await cq.edit_text(f"📝 Заметка сохранена (id={new_id})")
            logger.info("Capture→Note saved id=%s user_id=%s", new_id, user_id)

        else:
            await cq.edit_text("❌ Неизвестное действие.")
            logger.warning("Unknown capture kind: %s", kind)

        await cq.answer()

    except Exception as e:
        logger.exception("handle_capture_callback error: %s", e)
        try:
            await cq.answer("Ошибка при сохранении", show_alert=True)
        except Exception:
            pass

async def cleanup_expired_captures():
    now = datetime.now()
    expired = [cid for cid, (_, ts) in capture_store.items() if now - ts > CAPTURE_TTL]
    for cid in expired:
        text, _ = capture_store.pop(cid)
        logger.info("Expired capture removed: %s -> %s", cid, text[:50])


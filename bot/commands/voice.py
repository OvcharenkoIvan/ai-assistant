# bot/commands/voice.py
from __future__ import annotations

import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from bot.voice.state import set_voice_mode, is_voice_on

logger = logging.getLogger(__name__)

# ==========================
# Постоянная клавиатура для голосового режима
# ==========================
voice_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔊 Включить голос"), KeyboardButton("🔇 Выключить голос")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

# ==========================
# Основные функции: Вкл/Выкл голос
# ==========================

async def voice_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включить голосовой режим (для ответов бота)."""
    if not update.message:
        return
    try:
        user_id = update.effective_user.id
        set_voice_mode(user_id, True)
        await update.message.reply_text(
            "🔊 Голосовой режим включён.\nТеперь ответы будут приходить и в аудио.",
            reply_markup=voice_keyboard,
        )
        logger.info("User %s включил голосовой режим.", user_id)
    except Exception as e:
        logger.exception("Ошибка при включении голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка при включении голосового режима: {e}")


async def voice_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выключить голосовой режим."""
    if not update.message:
        return
    try:
        user_id = update.effective_user.id
        set_voice_mode(user_id, False)
        await update.message.reply_text(
            "🔇 Голосовой режим выключен.\nТеперь отправляю только текст.",
            reply_markup=voice_keyboard,
        )
        logger.info("User %s выключил голосовой режим.", user_id)
    except Exception as e:
        logger.exception("Ошибка при выключении голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка при выключении голосового режима: {e}")

# ==========================
# Статус голосового режима
# ==========================

async def voice_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущий статус голосового режима."""
    if not update.message:
        return
    try:
        user_id = update.effective_user.id
        status_bool = is_voice_on(user_id)
        status = "включён ✅" if status_bool else "выключен ❌"
        await update.message.reply_text(
            f"ℹ️ Голосовой режим сейчас {status}.\n"
            f"Используй кнопки ниже, чтобы включить или выключить.",
            reply_markup=voice_keyboard,
        )
        logger.info("User %s запросил статус голосового режима: %s", user_id, status)
    except Exception as e:
        logger.exception("Ошибка при проверке голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка при проверке голосового режима: {e}")

# ==========================
# Постоянная клавиатура
# ==========================

async def voice_persistent_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет постоянную клавиатуру для управления голосом."""
    if not update.message:
        return
    try:
        await update.message.reply_text(
            "Клавиатура для управления голосом активирована.\n"
            "Используй кнопки, чтобы включать/выключать голосовой режим.",
            reply_markup=voice_keyboard,
        )
    except Exception as e:
        logger.exception("Ошибка при отображении постоянной клавиатуры")
        await update.message.reply_text(f"⚠️ Ошибка при отображении клавиатуры: {e}")

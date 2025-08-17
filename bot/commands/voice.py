# bot/commands/voice.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.voice.state import set_voice_mode, is_voice_on, request_audio

# ==========================
# Глобальный голосовой режим
# ==========================

async def voice_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включить постоянный голосовой режим для пользователя."""
    try:
        user_id = update.effective_user.id
        set_voice_mode(user_id, True)
        await update.message.reply_text("🔊 Голосовой режим включён. Теперь ответы будут и в аудио.")
        logging.info(f"User {user_id} включил голосовой режим.")
    except Exception as e:
        logging.exception("Ошибка при включении голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

async def voice_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выключить постоянный голосовой режим для пользователя."""
    try:
        user_id = update.effective_user.id
        set_voice_mode(user_id, False)
        await update.message.reply_text("🔇 Голосовой режим выключен. Отправляю только текст.")
        logging.info(f"User {user_id} выключил голосовой режим.")
    except Exception as e:
        logging.exception("Ошибка при выключении голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

async def voice_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущий статус голосового режима."""
    try:
        user_id = update.effective_user.id
        status = "включён" if is_voice_on(user_id) else "выключен"
        await update.message.reply_text(f"ℹ️ Голосовой режим сейчас {status}.")
        logging.info(f"User {user_id} запросил статус голосового режима: {status}")
    except Exception as e:
        logging.exception("Ошибка при проверке голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

# ==========================
# Единичный голосовой ответ
# ==========================

async def answer_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Активирует голос для следующего ответа (англ.)."""
    try:
        user_id = update.effective_user.id
        request_audio(user_id)
        await update.message.reply_text("🔊 Следующий ответ я отправлю в голосе!")
        logging.info(f"User {user_id} запросил единичный голосовой ответ (англ.)")
    except Exception as e:
        logging.exception("Ошибка при установке единичного голосового ответа")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

async def ответь_аудио(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Активирует голос для следующего ответа (рус.)."""
    try:
        user_id = update.effective_user.id
        request_audio(user_id)
        await update.message.reply_text("🔊 Следующий ответ я отправлю в голосе!")
        logging.info(f"User {user_id} запросил единичный голосовой ответ (рус.)")
    except Exception as e:
        logging.exception("Ошибка при установке единичного голосового ответа")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

# ==========================
# Inline-кнопки для управления голосом
# ==========================

async def voice_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает кнопки для управления голосовым режимом."""
    try:
        keyboard = [
            [
                InlineKeyboardButton("🔊 Включить голос", callback_data="voice_on"),
                InlineKeyboardButton("🔇 Выключить голос", callback_data="voice_off")
            ],
            [
                InlineKeyboardButton("🔔 Следующий ответ в голосе", callback_data="next_voice")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    except Exception as e:
        logging.exception("Ошибка при отображении inline-кнопок")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

async def voice_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия inline-кнопок с логированием и защитой."""
    try:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()  # закрывает "часики" у кнопки

        if query.data == "voice_on":
            set_voice_mode(user_id, True)
            logging.info(f"User {user_id} включил голос через кнопку")
            await query.edit_message_text("🔊 Голосовой режим включён. Теперь ответы будут и в аудио.")
        elif query.data == "voice_off":
            set_voice_mode(user_id, False)
            logging.info(f"User {user_id} выключил голос через кнопку")
            await query.edit_message_text("🔇 Голосовой режим выключен. Отправляю только текст.")
        elif query.data == "next_voice":
            request_audio(user_id)
            logging.info(f"User {user_id} запросил единичный голосовой ответ через кнопку")
            await query.edit_message_text("🔊 Следующий ответ я отправлю в голосе!")
    except Exception as e:
        logging.exception("Ошибка при обработке inline-кнопки")
        if update.callback_query:
            await update.callback_query.edit_message_text(f"⚠️ Ошибка: {e}")

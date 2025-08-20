# bot/commands/voice.py
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from bot.voice.state import set_voice_mode, is_voice_on, request_audio
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # Закомментировано, пока не используем inline

# ==========================
# Постоянная клавиатура для голосового режима
# ==========================
voice_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔊 Включить голос"), KeyboardButton("🔇 Выключить голос")],
        # [KeyboardButton("🔔 Следующий ответ в голосе")]  # Можно раскомментировать при необходимости
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# ==========================
# Основные функции: Вкл/Выкл голос
# ==========================
async def voice_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включить голосовой режим (для ответов бота)."""
    try:
        user_id = update.effective_user.id
        set_voice_mode(user_id, True)
        await update.message.reply_text("🔊 Голосовой режим включён. Теперь ответы будут и в аудио.",
                                        reply_markup=voice_keyboard)
        logging.info(f"User {user_id} включил голосовой режим.")
    except Exception as e:
        logging.exception("Ошибка при включении голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

async def voice_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выключить голосовой режим."""
    try:
        user_id = update.effective_user.id
        set_voice_mode(user_id, False)
        await update.message.reply_text("🔇 Голосовой режим выключен. Отправляю только текст.",
                                        reply_markup=voice_keyboard)
        logging.info(f"User {user_id} выключил голосовой режим.")
    except Exception as e:
        logging.exception("Ошибка при выключении голосового режима")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

# ==========================
# Статус голосового режима
# ==========================
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
# Единичный голосовой ответ (закомментирован пока)
# ==========================
# async def answer_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Активирует голос для следующего ответа (англ.)."""
#     ...
# async def ответь_аудио(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Активирует голос для следующего ответа (рус.)."""
#     ...

# ==========================
# Inline-кнопки (не используются)
# ==========================
# async def voice_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     ...
# async def voice_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     ...

# ==========================
# Постоянная клавиатура
# ==========================
async def voice_persistent_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет постоянную клавиатуру для управления голосом."""
    try:
        await update.message.reply_text("Клавиатура для управления голосом активирована:", reply_markup=voice_keyboard)
    except Exception as e:
        logging.exception("Ошибка при отображении постоянной клавиатуры")
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

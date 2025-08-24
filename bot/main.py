# bot/main.py
import sys
import asyncio
import logging
from pathlib import Path
from telegram import BotCommand, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from bot.memory.capture import handle_capture_callback
from bot.memory.intent import process_intent
from bot.commands.start_help import start, help_command
from bot.commands.voice import voice_on, voice_off, voice_status
from bot.gpt.chat import chat_with_gpt
from bot.voice.handler import handle_voice
from bot.core.config import TELEGRAM_TOKEN

# --- Настройка корня проекта ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# --- Owner ID ---
OWNER_ID = 423368779

# --- Проверка токена ---
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден")

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# --- Голосовая клавиатура ---
voice_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔊 Включить голос"), KeyboardButton("🔇 Выключить голос")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

async def send_owner_keyboard(app):
    """Отправляет голосовую клавиатуру владельцу бота при старте"""
    try:
        await app.bot.send_message(
            chat_id=OWNER_ID,
            text="Клавиатура для управления голосом активирована:",
            reply_markup=voice_keyboard
        )
        logging.info(f"📲 Клавиатура отправлена пользователю {OWNER_ID}")
    except Exception as e:
        logging.error(f"❌ Не удалось отправить клавиатуру владельцу: {e}")

async def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # --- Создаем приложение ---
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # --- Команды в меню бота ---
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Список команд"),
        BotCommand("voice_on", "Включить голосовые ответы"),
        BotCommand("voice_off", "Выключить голосовые ответы"),
        BotCommand("voice_status", "Проверить статус голосового режима"),
        BotCommand("keyboard", "Открыть клавиатуру управления"),
    ])

    # --- CommandHandler ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("voice_on", voice_on))
    app.add_handler(CommandHandler("voice_off", voice_off))
    app.add_handler(CommandHandler("voice_status", voice_status))

    # --- MessageHandler для кнопок клавиатуры ---
    app.add_handler(MessageHandler(filters.Regex("^🔊 Включить голос$"), voice_on))
    app.add_handler(MessageHandler(filters.Regex("^🔇 Выключить голос$"), voice_off))

    # --- Голосовые сообщения ---
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # --- Inline кнопки Smart Capture ---
    app.add_handler(CallbackQueryHandler(handle_capture_callback, pattern=r"^capture:"))

    # --- Текстовые сообщения: GPT + Smart Capture ---
    async def text_handler(update, context):
        message = update.message
        if not message or not message.text:
            return
        # 1. Обработка Smart Capture
        await process_intent(message)
        # 2. Обработка GPT
        await chat_with_gpt(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # --- Лог информации о боте ---
    me = await app.bot.get_me()
    logging.info(f"🤖 Бот запущен: @{me.username} (id={me.id})")

    # --- Отправляем клавиатуру владельцу ---
    await send_owner_keyboard(app)

    # --- Запуск бота ---
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "event loop is already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise

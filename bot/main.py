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

# --- Корень проекта для sys.path ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# --- Owner ID ---
OWNER_ID = 423368779 # ID владельца бота (для админских команд)

# --- Импорты конфигурации и модулей ---
from bot.core.config import TELEGRAM_TOKEN

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден")

# --- Импорты команд ---
from bot.commands.start_help import start, help_command

from bot.commands.voice import (
    voice_on,
    voice_off,
    voice_status,
)  

# --- Обработчики сообщений ---
from bot.gpt.chat import chat_with_gpt          # текст → GPT
from bot.voice.handler import handle_voice      # voice → STT → GPT → (TTS)

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# Клавиатура для голосового режима
voice_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔊 Включить голос"), KeyboardButton("🔇 Выключить голос")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False  # <- клавиатура не исчезает после нажатия
)

async def main():
    # Windows: корректная политика цикла событий
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # --- Команды бота в меню ---
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Запустить бота"),
            BotCommand("help", "Список команд"),
            BotCommand("voice_on", "Включить голосовые ответы"),
            BotCommand("voice_off", "Выключить голосовые ответы"),
            BotCommand("voice_status", "Проверить статус голосового режима"),
            BotCommand("keyboard", "Открыть клавиатуру управления"),
        ]
    )
    

    # --- Хендлеры команд ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))


    # --- Голосовые команды ---
    app.add_handler(CommandHandler("voice_on", voice_on))
    app.add_handler(CommandHandler("voice_off", voice_off))
    app.add_handler(CommandHandler("voice_status", voice_status))

    
    # Обработка кнопок (они прилетают как обычные сообщения)
    app.add_handler(MessageHandler(filters.Regex("^🔊 Включить голос$"), voice_on))
    app.add_handler(MessageHandler(filters.Regex("^🔇 Выключить голос$"), voice_off))

    # --- Голосовые сообщения ---
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # --- Текст → GPT (кроме команд) ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_gpt))

    # Лог информации о боте
    me = await app.bot.get_me()
    logging.info(f"🤖 Бот запущен: @{me.username} (id={me.id})")

# --- Отправляем клавиатуру владельцу при старте ---
    try:
        await app.bot.send_message(
            chat_id=OWNER_ID,
            text="Клавиатура для управления голосом активирована:",
            reply_markup=voice_keyboard
        )
        logging.info(f"📲 Клавиатура отправлена пользователю {OWNER_ID}")
    except Exception as e:
        logging.error(f"❌ Не удалось отправить клавиатуру: {e}")
        logging.info("Бот готов к работе!")
        
# --- Запуск бота на постоянное прослушивание ---
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

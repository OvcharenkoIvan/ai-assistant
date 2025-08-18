# bot/main.py
import sys
import asyncio
import logging
from pathlib import Path
from telegram import BotCommand
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

# --- Импорты конфигурации и модулей ---
from bot.core.config import TELEGRAM_TOKEN

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден")

# --- Импорты команд ---
from bot.commands.start_help import start, help_command
# from bot.commands.notes import note, notes, reset, search  # Временно отключено

from bot.commands.voice import (
    voice_on,
    voice_off,
    voice_status,
    answer_voice,
    ответь_аудио,
    voice_inline,
    voice_button_handler,
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
            BotCommand("answer_voice", "Следующий ответ будет в голосе"),
            BotCommand("reply_audio", "Следующий ответ будет в голосе (рус.)"),  # латиница в command
            BotCommand("voice_inline", "Открыть кнопки управления голосом"),
        ]
    )

    # --- Хендлеры команд ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    # app.add_handler(CommandHandler("note", note))     # временно отключено
    # app.add_handler(CommandHandler("notes", notes))   # временно отключено
    # app.add_handler(CommandHandler("reset", reset))   # временно отключено
    # app.add_handler(CommandHandler("search", search)) # временно отключено

    # --- Голосовые команды ---
    app.add_handler(CommandHandler("voice_on", voice_on))
    app.add_handler(CommandHandler("voice_off", voice_off))
    app.add_handler(CommandHandler("voice_status", voice_status))
    app.add_handler(CommandHandler("answer_voice", answer_voice))
    app.add_handler(CommandHandler("reply_audio", ответь_аудио))

    # --- Inline-кнопки ---
    app.add_handler(CommandHandler("voice_inline", voice_inline))
    app.add_handler(
        CallbackQueryHandler(
            voice_button_handler, pattern=r"^(voice_on|voice_off|next_voice)$"
        )
    )

    # --- Голосовые сообщения ---
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # --- Текст → GPT (кроме команд) ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_gpt))

    # Лог информации о боте
    me = await app.bot.get_me()
    logging.info(f"🤖 Бот запущен: @{me.username} (id={me.id})")

    await app.run_polling(drop_pending_updates=True, close_loop=False)


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

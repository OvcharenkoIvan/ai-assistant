# bot/main.py
import sys
import asyncio
import logging
from pathlib import Path
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# --- Корень проекта для sys.path ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# --- Импорты конфигурации и модулей ---
from bot.core.config import TELEGRAM_TOKEN

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден")

# --- Импорты команд ---
from bot.commands.start_help import start, help_command
# from bot.commands.notes import note, notes, reset, search  # Временно закомментировано для теста
from bot.commands.voice import voice_on, voice_off, voice_status, answer_voice, ответь_аудио
from bot.gpt.chat import chat_with_gpt
from bot.voice.handler import handle_voice

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

async def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # --- Команды бота ---
    await app.bot.set_my_commands([
        # BotCommand("start", "Запустить бота"),  # Временно закомментировано
        # BotCommand("note", "Сохранить заметку"),  # Временно закомментировано
        # BotCommand("notes", "Показать все заметки"),  # Временно закомментировано
        # BotCommand("search", "Искать заметки"),  # Временно закомментировано
        # BotCommand("reset", "Удалить все заметки"),  # Временно закомментировано
        BotCommand("help", "Список команд"),
        BotCommand("voice_on", "Включить голосовые ответы"),
        BotCommand("voice_off", "Выключить голосовые ответы"),
        BotCommand("voice_status", "Проверить статус голосового режима"),
        BotCommand("answer_voice", "Следующий ответ будет в голосе"),
        BotCommand("ответь_аудио", "Следующий ответ будет в голосе (рус.)"),
    ])

    # --- Хендлеры команд ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    # app.add_handler(CommandHandler("note", note))  # Временно закомментировано
    # app.add_handler(CommandHandler("notes", notes))  # Временно закомментировано
    # app.add_handler(CommandHandler("reset", reset))  # Временно закомментировано
    # app.add_handler(CommandHandler("search", search))  # Временно закомментировано

    # --- Голосовые команды ---
    app.add_handler(CommandHandler("voice_on", voice_on))
    app.add_handler(CommandHandler("voice_off", voice_off))
    app.add_handler(CommandHandler("voice_status", voice_status))
    app.add_handler(CommandHandler("answer_voice", answer_voice))
    app.add_handler(CommandHandler("ответь_аудио", ответь_аудио))

    # --- Голосовые сообщения ---
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # --- Хендлер для GPT на все текстовые сообщения (кроме команд) ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_gpt))

    logging.info("🤖 Бот запущен и готов к работе...")
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

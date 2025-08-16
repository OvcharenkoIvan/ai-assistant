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

from bot.commands.start_help import start, help_command
from bot.commands.notes import note, notes, reset, search
from bot.gpt.chat import chat_with_gpt

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
        BotCommand("start", "Запустить бота"),
        BotCommand("note", "Сохранить заметку"),
        BotCommand("notes", "Показать все заметки"),
        BotCommand("search", "Искать заметки"),
        BotCommand("reset", "Удалить все заметки"),
        BotCommand("help", "Список команд")
    ])

    # --- Хендлеры команд ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search))

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

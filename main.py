# bot/main.py
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional
from bot.memory.memory_sqlite import init_db

from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

# --- Корень проекта для sys.path ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# --- Импорты конфигурации и модулей ---
from bot.core.config import TELEGRAM_TOKEN
from bot.commands.start_help import start, help_command
from bot.commands.notes import note, notes, reset, search
from bot.gpt.chat import chat_with_gpt

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден в .env")


async def setup_bot_commands(app: Application) -> None:
    """
    Установка списка команд Telegram для интерфейса пользователя
    """
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Список команд"),
        BotCommand("note", "Сохранить заметку"),
        BotCommand("notes", "Показать все заметки"),
        BotCommand("search", "Искать заметки"),
        BotCommand("reset", "Удалить все заметки"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("✅ Команды бота успешно установлены.")


async def main() -> None:
    # --- Для Windows корректный event loop ---
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Инициализируем SQLite для assistant
    init_db()

    # --- Создание приложения ---
    app: Application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # --- Установка команд ---
    await setup_bot_commands(app)

    # --- Хендлеры команд ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search))

    # --- Хендлер для GPT на все текстовые сообщения (кроме команд) ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_gpt))

    logger.info("🤖 Бот запущен и готов к работе...")
    await app.run_polling(drop_pending_updates=True, close_loop=False)


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    try:
        asyncio.run(main())
    except RuntimeError as e:
        # Если loop уже запущен (например, в Jupyter), запускаем корректно
        if "event loop is already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise

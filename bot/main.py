# bot/main.py
import sys
import asyncio
import logging
from functools import partial
from pathlib import Path

from telegram import BotCommand, ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- Модули бота ---
from bot.memory.capture import handle_capture_callback
from bot.memory.intent import process_intent
from bot.commands.start_help import start, help_command
from bot.commands.voice import voice_on, voice_off, voice_status
from bot.commands import notes, tasks
from bot.gpt.chat import chat_with_gpt
from bot.memory.memory_loader import get_memory
from bot.core.config import TELEGRAM_TOKEN

# --- Настройка корня проекта ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# --- Owner ID (для клавиатуры управления голосом) ---
OWNER_ID = 423368779

# --- Проверка токена перед запуском ---
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден")

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# --- Клавиатура для голосового управления ---
voice_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("🔊 Включить голос"), KeyboardButton("🔇 Выключить голос")]],
    resize_keyboard=True,
    one_time_keyboard=False
)

# --- Инициализация памяти ---
_mem = get_memory()  # Возвращает экземпляр MemorySQLite или аналогичного класса


async def send_owner_keyboard(app):
    """Отправляет владельцу бота клавиатуру для голосового управления"""
    try:
        await app.bot.send_message(
            chat_id=OWNER_ID,
            text="Клавиатура для управления голосом активирована:",
            reply_markup=voice_keyboard
        )
        logging.info(f"📲 Клавиатура отправлена пользователю {OWNER_ID}")
    except Exception as e:
        logging.error(f"❌ Не удалось отправить клавиатуру владельцу: {e}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик текстовых сообщений:
    1. Пробуем понять интент через process_intent (Smart Capture)
    2. Если интент не распознан, отправляем на GPT
    """
    if not update.message or not update.message.text:
        return

    handled = await process_intent(update.message)
    if not handled:
        await chat_with_gpt(update, context)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок для логирования и безопасности продакшн"""
    logging.error(f"❌ Ошибка обработки обновления: {update}", exc_info=context.error)


async def main():
    """Главная функция запуска бота"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # --- Создаем приложение ---
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # --- Настройка меню команд бота ---
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Список команд"),
        BotCommand("voice_on", "Включить голосовые ответы"),
        BotCommand("voice_off", "Выключить голосовые ответы"),
        BotCommand("voice_status", "Проверить статус голосового режима"),
        BotCommand("keyboard", "Открыть клавиатуру управления"),
        BotCommand("note", "Сохранить заметку"),
        BotCommand("notes", "Показать все заметки"),
        BotCommand("search", "Поиск заметок"),
        BotCommand("reset", "Удалить все заметки"),
        BotCommand("task", "Добавить задачу"),
        BotCommand("tasks", "Показать все задачи"),
        BotCommand("reset_tasks", "Удалить все задачи"),
    ])

    # --- Глобальный обработчик ошибок ---
    app.add_error_handler(error_handler)

    # --- CommandHandler для стандартных команд ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("voice_on", voice_on))
    app.add_handler(CommandHandler("voice_off", voice_off))
    app.add_handler(CommandHandler("voice_status", voice_status))

    # --- Notes: используем partial для передачи _mem ---
    app.add_handler(CommandHandler("note", partial(notes.note, _mem=_mem)))
    app.add_handler(CommandHandler("notes", partial(notes.notes, _mem=_mem)))
    app.add_handler(CommandHandler("reset", partial(notes.reset, _mem=_mem)))
    app.add_handler(CommandHandler("search", partial(notes.search, _mem=_mem)))

    # --- Tasks: partial для передачи _mem ---
    app.add_handler(CommandHandler("task", partial(tasks.add_task_command, _mem=_mem)))
    app.add_handler(CommandHandler("tasks", partial(tasks.tasks, _mem=_mem)))
    app.add_handler(CommandHandler("reset_tasks", partial(tasks.reset_tasks, _mem=_mem)))

    # --- Голосовые команды через клавиатуру ---
    app.add_handler(MessageHandler(filters.Regex("^🔊 Включить голос$"), voice_on))
    app.add_handler(MessageHandler(filters.Regex("^🔇 Выключить голос$"), voice_off))

    # --- Inline кнопки Smart Capture ---
    app.add_handler(CallbackQueryHandler(handle_capture_callback, pattern=r"^capture:"))

    # --- Текстовые сообщения: GPT + Smart Capture ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # --- Запуск бота и отправка клавиатуры владельцу ---
    me = await app.bot.get_me()
    logging.info(f"🤖 Бот запущен: @{me.username} (id={me.id})")
    await send_owner_keyboard(app)
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
# bot/memory/capture.py
import asyncio
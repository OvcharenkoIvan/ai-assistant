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
from bot.core.config import TELEGRAM_TOKEN, OWNER_ID, LOG_LEVEL

# 🔔 Планировщик (pull-sync Google + дайджесты + бэкапы)
from bot.scheduler.scheduler import start_scheduler

# 🧩 Действия с задачами (перенос/выполнить/удалить) + перехват текста для рескейджла
from bot.commands.task_actions import handle_task_action_callback, handle_reschedule_text

# --- Настройка корня проекта ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# --- Owner ID (клавиатура и админ-уведомления) ---
OWNER_ID = OWNER_ID or 0

# --- Проверка токена перед запуском ---
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден")

# --- Настройка логирования ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
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
_mem = get_memory()  # общий адаптер MemorySQLite / InMemory


async def send_owner_keyboard(app):
    """Отправляет владельцу бота клавиатуру для голосового управления"""
    if not OWNER_ID:
        return
    try:
        await app.bot.send_message(
            chat_id=OWNER_ID,
            text="Клавиатура для управления голосом активирована:",
            reply_markup=voice_keyboard
        )
        logging.info("📲 Клавиатура отправлена владельцу")
    except Exception as e:
        logging.error(f"❌ Не удалось отправить клавиатуру владельцу: {e}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    1) Если ждём новую дату/время для переноса — обрабатываем и выходим.
    2) Иначе: Smart Capture → GPT.
    """
    processed = await handle_reschedule_text(update, context, _mem=_mem)
    if processed:
        return

    if not update.message or not update.message.text:
        return

    handled = await process_intent(update.message)
    if not handled:
        await chat_with_gpt(update, context)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logging.error(f"❌ Ошибка обработки обновления: {update}", exc_info=context.error)


async def main():
    """Главная функция запуска бота"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # --- Создаем приложение ---
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # --- Меню команд ---
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
        BotCommand("complete", "Отметить задачу выполненной"),
    ])

    # --- Ошибки ---
    app.add_error_handler(error_handler)

    # --- Commands ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("voice_on", voice_on))
    app.add_handler(CommandHandler("voice_off", voice_off))
    app.add_handler(CommandHandler("voice_status", voice_status))

    # --- Notes ---
    app.add_handler(CommandHandler("note", partial(notes.note, _mem=_mem)))
    app.add_handler(CommandHandler("notes", partial(notes.notes, _mem=_mem)))
    app.add_handler(CommandHandler("reset", partial(notes.reset, _mem=_mem)))
    app.add_handler(CommandHandler("search", partial(notes.search, _mem=_mem)))

    # --- Tasks ---
    app.add_handler(CommandHandler("task", partial(tasks.add_task_command, _mem=_mem)))
    app.add_handler(CommandHandler("tasks", partial(tasks.tasks, _mem=_mem)))
    app.add_handler(CommandHandler("reset_tasks", partial(tasks.reset_tasks, _mem=_mem)))
    app.add_handler(CommandHandler("complete", partial(tasks.complete_task, _mem=_mem)))

    # --- Голосовые кнопки ---
    app.add_handler(MessageHandler(filters.Regex("^🔊 Включить голос$"), voice_on))
    app.add_handler(MessageHandler(filters.Regex("^🔇 Выключить голос$"), voice_off))

    # --- Smart Capture ---
    app.add_handler(CallbackQueryHandler(handle_capture_callback, pattern=r"^capture:"))

    # --- Task Actions ---
    app.add_handler(CallbackQueryHandler(partial(handle_task_action_callback, _mem=_mem), pattern=r"^task_action:"))

    # --- Текстовые сообщения: GPT + Smart Capture ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # --- Запуск бота ---
    me = await app.bot.get_me()
    logging.info(f"🤖 Бот запущен: @{me.username} (id={me.id})")
    await send_owner_keyboard(app)

    # --- Планировщик: pull-sync + дайджесты + бэкапы ---
    start_scheduler(app, _mem, OWNER_ID)

    # --- Polling ---
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

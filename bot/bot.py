import sys
import asyncio
import os
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
from core import storage
from core.logger import log_action

# Установка политики цикла событий для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я твой ассистент по заметкам.\n\n"
        "📌 /note <текст> — сохранить заметку\n"
        "📜 /notes — показать все заметки\n"
        "🔍 /search <ключевое слово> — поиск заметок\n"
        "🗑 /reset — удалить все заметки\n"
        "ℹ️ /help — список команд\n\n"
        "Выбирай команду из меню ниже ⬇"
    )
    log_action(f"User {update.effective_user.id} запустил /start")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "• /note <текст> — сохранить заметку\n"
        "• /notes — показать все заметки\n"
        "• /search <ключевое слово> — поиск заметок\n"
        "• /reset — удалить все заметки"
    )

async def note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    note_text = " ".join(context.args).strip()
    if not note_text:
        await update.message.reply_text("⚠️ Пожалуйста, добавь текст заметки после команды /note")
        return
    storage.add_note(user_id, note_text)
    log_action(f"User {user_id} добавил заметку: {note_text}")
    await update.message.reply_text("✅ Заметка сохранена!")

async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notes = storage.get_notes(user_id)
    if not notes:
        await update.message.reply_text("📭 У тебя пока нет заметок.")
        return
    max_notes = 20
    limited_notes = notes[:max_notes]
    msg = "\n".join(f"{i+1}. {n}" for i, n in enumerate(limited_notes, start=1))
    if len(notes) > max_notes:
        msg += f"\n\n⚠️ Показаны только первые {max_notes} заметок из {len(notes)}."
    await update.message.reply_text("📝 Твои заметки:\n" + msg)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    storage.reset_notes(user_id)
    log_action(f"User {user_id} удалил все заметки")
    await update.message.reply_text("🗑 Все заметки удалены.")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("⚠️ Укажи ключевое слово: /search <слово>")
        return
    results = storage.search_notes(user_id, keyword)
    log_action(f"User {user_id} выполнил поиск по ключу: {keyword}")
    if results:
        msg = "\n".join(f"{i+1}. {note}" for i, note in enumerate(results, start=1))
        await update.message.reply_text("🔍 Результаты поиска:\n" + msg)
    else:
        await update.message.reply_text("❌ Ничего не найдено.")

# --- Основная функция запуска бота ---

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Установка команд бота
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота"),
        BotCommand("note", "Сохранить заметку"),
        BotCommand("notes", "Показать все заметки"),
        BotCommand("search", "Искать заметки"),
        BotCommand("reset", "Удалить все заметки"),
        BotCommand("help", "Список команд"),
    ])

    # Регистрация обработчиков команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search))

    print("🚀 Бот запущен...")
    await app.run_polling()

# Точка входа
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

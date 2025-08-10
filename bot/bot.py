import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
from core import storage

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой ассистент. Вот что я умею:\n"
        "/note <текст> — сохранить заметку\n"
        "/notes — показать все заметки\n"
        "/reset — удалить все заметки\n"
        "/help — список команд"
    )

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/note <текст> — сохранить заметку\n"
        "/notes — показать все заметки\n"
        "/reset — удалить все заметки"
    )

# /note
async def note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    note_text = " ".join(context.args)
    if not note_text:
        await update.message.reply_text("Пожалуйста, добавь текст заметки после команды /note")
        return
    storage.add_note(user_id, note_text)
    await update.message.reply_text("Заметка сохранена!")

# /notes
async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notes = storage.get_notes(user_id)
    if not notes:
        await update.message.reply_text("У тебя пока нет заметок.")
        return
    msg = "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
    await update.message.reply_text("Твои заметки:\n" + msg)

# /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    storage.reset_notes(user_id)
    await update.message.reply_text("Все заметки удалены.")

# Запуск бота
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("reset", reset))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

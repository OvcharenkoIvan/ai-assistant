from telegram import Update
from telegram.ext import ContextTypes
from bot.core.logger import log_action

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я твой ассистент.\n"
        "Меню команд:\n"
        "📌 /note <текст> — сохранить заметку\n"
        "📜 /notes — показать все заметки\n"
        "🔍 /search <ключевое слово> — поиск заметок\n"
        "🗑 /reset — удалить все заметки\n"
        "ℹ️ /help — список команд\n\n"
        "💬 Просто напиши вопрос — я отвечу через GPT."
    )
    log_action(f"User {update.effective_user.id} запустил /start")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "• /note <текст> — сохранить заметку\n"
        "• /notes — показать все заметки\n"
        "• /search <ключевое слово> — поиск заметок\n"
        "• /reset — удалить все заметки\n\n"
        "💬 Или задай вопрос — отвечу через GPT."
    )

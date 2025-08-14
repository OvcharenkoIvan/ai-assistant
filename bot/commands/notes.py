from telegram import Update
from telegram.ext import ContextTypes
from bot.core import storage
from bot.core.logger import log_action

async def note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("⚠️ Добавь текст после /note")
        return
    storage.add_note(user_id, text)
    log_action(f"User {user_id} добавил заметку: {text}")
    await update.message.reply_text("✅ Заметка сохранена!")

async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notes = storage.get_notes(user_id)
    if not notes:
        await update.message.reply_text("📭 Заметок нет.")
        return
    msg = "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes[:20], 1))
    if len(notes) > 20:
        msg += f"\n\n⚠️ Показаны первые 20 из {len(notes)}"
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
    log_action(f"User {user_id} поиск: {keyword}")
    if results:
        msg = "\n".join(f"{i+1}. {n}" for i, n in enumerate(results, 1))
        await update.message.reply_text("🔍 Результаты поиска:\n" + msg)
    else:
        await update.message.reply_text("❌ Ничего не найдено.")

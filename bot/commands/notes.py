# bot/commands/notes.py
from telegram import Update
from telegram.ext import ContextTypes
from bot.memory.memory_loader import get_memory
from bot.core.logger import log_action

# Singleton memory instance
_mem = get_memory()


async def note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Добавляет заметку пользователя.
    Команда: /note <текст>
    """
    user_id = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("⚠️ Добавь текст после /note")
        return

    note_id = await _mem.add_note(user_id=user_id, text=text)
    log_action(f"User {user_id} добавил заметку (id={note_id}): {text}")
    await update.message.reply_text("✅ Заметка сохранена!")


async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Выводит все заметки пользователя.
    Команда: /notes
    """
    user_id = update.effective_user.id
    notes_list = await _mem.list_notes(user_id=user_id)
    if not notes_list:
        await update.message.reply_text("📭 Заметок нет.")
        return

    msg = "\n".join(f"{i+1}. {n.text}" for i, n in enumerate(notes_list[:20]))
    if len(notes_list) > 20:
        msg += f"\n\n⚠️ Показаны первые 20 из {len(notes_list)}"
    await update.message.reply_text("📝 Твои заметки:\n" + msg)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Удаляет все заметки пользователя.
    Команда: /reset
    """
    user_id = update.effective_user.id
    notes_list = await _mem.list_notes(user_id=user_id)
    for n in notes_list:
        await _mem.delete_note(n.id)
    log_action(f"User {user_id} удалил все заметки")
    await update.message.reply_text("🗑 Все заметки удалены.")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Поиск заметок по ключевому слову.
    Команда: /search <слово>
    """
    user_id = update.effective_user.id
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("⚠️ Укажи ключевое слово: /search <слово>")
        return

    notes_list = await _mem.list_notes(user_id=user_id)
    results = [n for n in notes_list if keyword.lower() in n.text.lower()]
    log_action(f"User {user_id} поиск заметок: {keyword}")

    if results:
        msg = "\n".join(f"{i+1}. {n.text}" for i, n in enumerate(results[:20]))
        if len(results) > 20:
            msg += f"\n\n⚠️ Показаны первые 20 из {len(results)}"
        await update.message.reply_text("🔍 Результаты поиска:\n" + msg)
    else:
        await update.message.reply_text("❌ Ничего не найдено.")

import sys
import asyncio
import os
import logging

from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

# Локальные модули
from core import storage
from core.logger import log_action

# GPT (новый официальный клиент OpenAI)
from openai import OpenAI

# -----------------------------
# Настройки и инициализация
# -----------------------------
# Политика цикла событий (Windows fix)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)

# Загрузка .env
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN не найден в .env")
if not OPENAI_API_KEY:
    logging.warning("⚠️ OPENAI_API_KEY не найден — GPT-ответы работать не будут.")

# Инициализация OpenAI-клиента (если ключ есть)
client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# Обработчики команд
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я твой ассистент.\n\n"
        "Меню команд:\n"
        "📌 /note <текст> — сохранить заметку\n"
        "📜 /notes — показать все заметки\n"
        "🔍 /search <ключевое слово> — поиск заметок\n"
        "🗑 /reset — удалить все заметки\n"
        "ℹ️ /help — список команд\n\n"
        "💬 Также можешь просто написать вопрос — я отвечу через GPT."
    )
    log_action(f"User {update.effective_user.id} запустил /start")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "• /note <текст> — сохранить заметку\n"
        "• /notes — показать все заметки\n"
        "• /search <ключевое слово> — поиск заметок\n"
        "• /reset — удалить все заметки\n\n"
        "💬 Или просто задай вопрос — отвечу через GPT (если настроен ключ)."
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

# -----------------------------
# GPT — обработка обычного текста
# -----------------------------
async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if client is None:
        await update.message.reply_text("⚠️ GPT не настроен. Добавь OPENAI_API_KEY в .env")
        return

    user_id = update.effective_user.id
    user_message = (update.message.text or "").strip()
    if not user_message:
        return

    try:
        # Модель можно поменять на "gpt-4o" или "gpt-4o-mini"
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты — Spudnyk, персональный ассистент Ивана. "
                        "Отвечай кратко, по делу, дружелюбно. "
                        "Если пользователь просит — давай расширенные инструкции."
                        "Всегда помни, что ты — AI-помощник, созданный для помощи Ивану Овчаренко."
                        "Всегда говори только правду и не выдумывай факты, если не знаешь ответа."
                        "Выдавай только проверенную информацию и не делай предположений если тебя не попросят (если спросят твое предложение - дай его)."
                        "Если чего-то не знаешь или не можешь найти - говори правду, не пытайся выдумывать ответ."
                        "Ты полноценный помощник, ассистент, который всеми путями хочет искренне помочь своему владельцу Ивану Овчаренко."
                    ),
                },
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=700,
        )
        bot_reply = response.choices[0].message.content
        log_action(f"GPT ответил пользователю {user_id} на запрос: {user_message}")
        await update.message.reply_text(bot_reply)
    except Exception as e:
        logging.exception("Ошибка GPT")
        await update.message.reply_text(f"⚠️ Ошибка при обращении к GPT: {e}")

# -----------------------------
# Запуск приложения
# -----------------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Меню команд
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота"),
        BotCommand("note", "Сохранить заметку"),
        BotCommand("notes", "Показать все заметки"),
        BotCommand("search", "Искать заметки"),
        BotCommand("reset", "Удалить все заметки"),
        BotCommand("help", "Список команд"),
    ])

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search))

    # GPT: отвечаем на любое сообщение, кроме команд
    app.add_handler(MessageHandler(~filters.COMMAND, chat_with_gpt))

    logging.info("🤖 Бот запущен...")
    await app.run_polling(close_loop=False, drop_pending_updates=True)

# Точка входа
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

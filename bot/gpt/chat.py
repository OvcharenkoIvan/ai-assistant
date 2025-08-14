import os
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from openai import OpenAI
from bot.core import storage
from bot.core.logger import log_action
from dotenv import load_dotenv

# --- Корень проекта для dotenv и sys.path ---
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not OPENAI_API_KEY:
    logging.warning("⚠️ OPENAI_API_KEY не найден! GPT не будет работать.")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = (
    "Ты — Spudnyk, персональный ассистент Ивана. "
    "Отвечай кратко, по делу, дружелюбно. "
    "Если пользователь просит — давай расширенные инструкции. "
    "Всегда помни, что ты — AI-помощник для Иванa Овчаренко. "
    "Говори только правду, не выдумывай факты. "
    "Ты полноценный помощник, который всеми путями хочет искренне помочь."
)

async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if client is None:
        await update.message.reply_text("⚠️ GPT не настроен.")
        return
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text: return
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.7,
            max_tokens=700
        )
        bot_reply = resp.choices[0].message.content
        log_action(f"GPT ответ пользователю {user_id} на: {text}")
        await update.message.reply_text(bot_reply)
    except Exception as e:
        logging.exception("Ошибка GPT")
        await update.message.reply_text(f"⚠️ Ошибка GPT: {e}")

from telegram import Update
from telegram.ext import ContextTypes
from openai import OpenAI
import logging

from bot.core.logger import log_action
from bot.core.config import (
    SYSTEM_PROMPT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
)

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if client is None:
    logging.warning("⚠️ OPENAI_API_KEY не найден — GPT-ответы будут отключены.")

async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, что это текстовое сообщение
    if not update.message or not update.message.text:
        return

    # Игнорируем команды (начинаются с /)
    if update.message.text.startswith("/"):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    logging.info(f"Получено сообщение от {user_id}: {text}")

    if client is None:
        await update.message.reply_text("⚠️ GPT не настроен (нет ключа API).")
        return

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
        )
        reply = resp.choices[0].message.content
        log_action(f"GPT ответ пользователю {user_id}: {text[:120]!r}")
        await update.message.reply_text(reply)

    except Exception as e:
        logging.exception("Ошибка GPT")
        await update.message.reply_text(f"⚠️ Ошибка GPT: {e}")

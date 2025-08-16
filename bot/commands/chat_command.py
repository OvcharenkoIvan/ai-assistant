from telegram import Update
from telegram.ext import ContextTypes
import logging

from bot.core.logger import log_action
from bot.gpt.chat import build_messages, ask_gpt


async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хендлер Telegram — только разбор входного сообщения и вызов GPT через chat.py
    """
    if not update.message or not update.message.text:
        return

    if update.message.text.startswith("/"):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    logging.info(f"Получено сообщение от {user_id}: {text}")

    messages = build_messages(user_id, text)
    reply = ask_gpt(messages)
    log_action(f"GPT ответ пользователю {user_id}: {text[:120]!r}")
    await update.message.reply_text(reply)

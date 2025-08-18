# bot/gpt/chat.py
from telegram import Update
from telegram.ext import ContextTypes
from openai import OpenAI
import logging

from bot.core.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
)
from bot.gpt.prompt import SYSTEM_PROMPT
from bot.voice.state import should_send_voice_now
from bot.voice.tts import synthesize_and_send_voice  # единая точка для TTS

# --- Инициализация клиента OpenAI ---
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if client is None:
    logging.warning("⚠️ OPENAI_API_KEY не найден — GPT-ответы будут отключены.")


# --- Строим список сообщений для GPT ---
def build_messages(user_id: int, user_text: str):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]


# --- Запрос к GPT через OpenAI API ---
def ask_gpt(messages):
    if client is None:
        raise RuntimeError("OpenAI API ключ не настроен")
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
    )
    return resp.choices[0].message.content


# --- Обёртка для Telegram ---
async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith("/"):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    logging.info(f"Получено сообщение от {user_id}: {text}")

    if client is None:
        await update.message.reply_text("⚠️ GPT не настроен (нет ключа API).")
        return

    try:
        messages = build_messages(user_id, text)
        reply = ask_gpt(messages)
        logging.info(f"GPT ответ пользователю {user_id}: {reply[:120]!r}")

        # Всегда отправляем текст
        await update.message.reply_text(reply)

        # Если голос включён глобально или разово → отправляем TTS
        if should_send_voice_now(user_id):
            try:
                await synthesize_and_send_voice(update, reply)
            except Exception:
                logging.exception("Ошибка TTS при ответе на текстовое сообщение")

    except Exception as e:
        logging.exception("Ошибка GPT")
        await update.message.reply_text(f"⚠️ Ошибка GPT: {e}")

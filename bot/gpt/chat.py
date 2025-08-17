# bot/gpt/chat.py
from telegram import Update
from telegram.ext import ContextTypes
from openai import OpenAI
import logging
from pathlib import Path
from datetime import datetime

from bot.core.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
    UPLOADS_DIR,  # папка для сохранения mp3
)
from bot.gpt.prompt import SYSTEM_PROMPT
from bot.voice.state import is_voice_on, clear_audio_request
from bot.voice.tts import speak  # твоя функция TTS


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
    # Проверяем, что это текстовое сообщение и не команда
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

        # Отправляем текст
        await update.message.reply_text(reply)

        # Проверяем, нужно ли отправить аудио (следующий ответ в голосе)
        if is_voice_on(user_id):
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                user_dir = Path(UPLOADS_DIR) / str(user_id)
                user_dir.mkdir(parents=True, exist_ok=True)
                mp3_out_path = user_dir / f"{ts}_reply_text.mp3"

                # Генерация аудио через TTS
                await speak(reply, mp3_out_path.as_posix())

                # Отправка аудио в Telegram
                with mp3_out_path.open("rb") as f:
                    await update.message.reply_audio(
                        audio=f,
                        caption="🔊 Аудио-ответ",
                        title=f"reply_{ts}.mp3",
                    )
            except Exception as e:
                logging.exception("Ошибка TTS при ответе на текстовое сообщение")
            finally:
                # Сбрасываем флаг, чтобы следующий ответ был обычным текстом
                clear_audio_request(user_id)

    except Exception as e:
        logging.exception("Ошибка GPT")
        await update.message.reply_text(f"⚠️ Ошибка GPT: {e}")

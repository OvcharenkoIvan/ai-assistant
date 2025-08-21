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
    AUTO_WEB,
    SEARCH_LOCALE,
    SEARCH_COUNTRY,
)
from bot.gpt.prompt import SYSTEM_PROMPT
from bot.voice.state import should_send_voice_now
from bot.voice.tts import synthesize_and_send_voice
from bot.search.web import web_search, render_results_for_prompt
from bot.gpt.translate import translate_text

logger = logging.getLogger(__name__)

# --- Инициализация клиента OpenAI ---
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if client is None:
    logger.warning("⚠️ OPENAI_API_KEY не найден — GPT-ответы будут отключены.")


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

# --- Строим список сообщений для GPT с web-контекстом ---
def build_messages(user_id: int, user_text: str, web_text: str = ""):
    if web_text:
        user_content = f"Используй актуальную информацию из интернета:\n{web_text}\n\nВопрос пользователя:\n{user_text}"
    else:
        user_content = user_text

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

# --- Ключевые слова для web search ---
WEB_KEYWORDS = [
    "сейчас", "сегодня", "новости", "последние", "актуальные",
    "кто", "кто руководит",
    "какой день", "какая дата", "какой праздник",
    "когда будет", "расписание",
    "погода", "курс валют", "евро", "доллар", "биткоин", "акции",
    "где находится", "адрес", "магазин", "ресторан", "кафе", "рядом",
    "фильм", "сериал", "песня", "певец", "актёр", "актриса", "тур", "концерт",
    "матч", "счёт", "турнир", "чемпионат", "лига", "результат"
]

def needs_web_search(user_text: str) -> bool:
    text = user_text.lower()
    for kw in WEB_KEYWORDS:
        if kw in text:
            return True
    # эвристика: короткие вопросы с "?"
    if len(text.split()) <= 5 and text.endswith("?"):
        return True
    return False

# --- Обёртка для Telegram ---
async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith("/"):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    logger.info(f"Получено сообщение от {user_id}: {text!r}")

    if client is None:
        await update.message.reply_text("⚠️ GPT не настроен (нет ключа API).")
        return

    web_text = ""
    if AUTO_WEB and needs_web_search(text):
        try:
            results = web_search(
                query=text,
                max_results=5,
                lang=SEARCH_LOCALE,
                country=SEARCH_COUNTRY,
            )
            if results:
                web_text = render_results_for_prompt(results)
                web_text = await translate_text(web_text, target_language="Russian")
        except Exception as e:
            logger.warning(f"Web search failed: {e}")

    try:
        messages = build_messages(user_id, text, web_text)
        reply = ask_gpt(messages)
        logger.info(f"GPT ответ пользователю {user_id}: {reply[:120]!r}")

        # Отправляем текст
        await update.message.reply_text(reply)

        # Отправка TTS, если включено
        if should_send_voice_now(user_id):
            try:
                await synthesize_and_send_voice(update, reply)
            except Exception:
                logger.exception("Ошибка TTS при ответе на текстовое сообщение")

    except Exception as e:
        logger.exception("Ошибка GPT")
        await update.message.reply_text(f"⚠️ Ошибка GPT: {e}")

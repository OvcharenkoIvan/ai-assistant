from __future__ import annotations
import asyncio
import inspect
import logging
from typing import List, Dict

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import AUTO_WEB, SEARCH_LOCALE, SEARCH_COUNTRY
from bot.gpt.client import ask_gpt, is_configured
from bot.gpt.prompt import get_core_prompt, get_tasks_prompt, get_notes_prompt
from bot.gpt.translate import translate_text
from bot.voice.state import should_send_voice_now
from bot.voice.tts import synthesize_and_send_voice
from bot.search.web import web_search, render_results_for_prompt

logger = logging.getLogger(__name__)

# --- Ключевые слова для web search ---
WEB_KEYWORDS = [
    "сейчас", "сегодня", "новости", "последние", "актуальные",
    "кто", "кто руководит",
    "какой день", "какая дата", "какой праздник",
    "когда будет", "расписание",
    "погода", "курс валют", "евро", "доллар", "биткоин", "акции",
    "где находится", "адрес", "магазин", "ресторан", "кафе", "рядом",
    "фильм", "сериал", "песня", "певец", "актёр", "актриса", "тур", "концерт",
    "матч", "счёт", "турнир", "чемпионат", "лига", "результат",
]

# --- Определяем режим GPT ---
def detect_mode(user_text: str) -> str:
    """
    Возвращает один из режимов: "tasks" | "notes" | "default".
    Эвристика:
      - явные глаголы/существительные -> tasks/notes
      - иначе default
    """
    t = (user_text or "").lower()

    task_hits = any(kw in t for kw in [
        "задач", "напомни", "напомните", "сделать", "сделай", "todo", "to do", "дедлайн", "план"
    ])
    note_hits = any(kw in t for kw in [
        "заметк", "запиши", "сохрани", "идея", "мысл", "пометка"
    ])

    if task_hits and not note_hits:
        return "tasks"
    if note_hits and not task_hits:
        return "notes"
    return "default"

# --- Строим список сообщений для GPT с web-контекстом ---
def build_messages(user_id: int, user_text: str, web_text: str = "", mode: str = "default"):
    """
    Формирует system + user для GPT с учётом режима:
    - default → только core
    - tasks → core + tasks
    - notes → core + notes
    """
    core = get_core_prompt()
    if mode == "tasks":
        role = get_tasks_prompt()
    elif mode == "notes":
        role = get_notes_prompt()
    else:
        role = ""

    system_prompt = f"{core}\n\n---\n{role}" if role else core

    if web_text:
        user_content = (
            f"Используй актуальную информацию из интернета:\n{web_text}\n\n"
            f"Вопрос пользователя:\n{user_text}"
        )
    else:
        user_content = user_text

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

# --- Эвристика web search ---
def needs_web_search(user_text: str) -> bool:
    text = (user_text or "").lower()
    for kw in WEB_KEYWORDS:
        if kw in text:
            return True
    if len(text.split()) <= 5 and text.endswith("?"):
        return True
    return False

# --- Основной обработчик Telegram ---
async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith("/"):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    logger.info("Получено сообщение от %s: %r", user_id, text)

    if not is_configured():
        await update.message.reply_text("⚠️ GPT не настроен (нет ключа API).")
        return

    mode = detect_mode(text)  # <-- выбор режима GPT

    web_text = ""
    if AUTO_WEB and needs_web_search(text):
        try:
            if inspect.iscoroutinefunction(web_search):
                results = await web_search(
                    query=text,
                    max_results=5,
                    lang=SEARCH_LOCALE,
                    country=SEARCH_COUNTRY,
                )
            else:
                results = await asyncio.to_thread(
                    web_search,
                    text,
                    5,
                    SEARCH_LOCALE,
                    SEARCH_COUNTRY,
                )
            if results:
                web_text = render_results_for_prompt(results)
                try:
                    web_text = await translate_text(web_text, target_language="Russian")
                except Exception:
                    logger.exception("Ошибка перевода web-контента; использую оригинал")
        except Exception as e:
            logger.warning("Web search failed: %s", e)

    try:
        messages = build_messages(user_id, text, web_text, mode=mode)
        reply = await ask_gpt(messages)
        logger.info("GPT ответ пользователю %s: %r", user_id, (reply[:120] if reply else reply))

        await update.message.reply_text(reply)

        if should_send_voice_now(user_id):
            try:
                await synthesize_and_send_voice(update, reply)
            except Exception:
                logger.exception("Ошибка TTS при ответе на текстовое сообщение")

    except Exception as e:
        logger.exception("Ошибка GPT при обработке сообщения")
        await update.message.reply_text(f"⚠️ Ошибка GPT: {e}")

# bot/memory/formatters.py
"""
Formatters: расширяемое форматирование текста через GPT + fallback.
Поддержка типов:
- email: subject, body, to[], due_at
- meeting: tasks [{task, due_at}], notes
- vector: подготовка текста для embedding (lowercase, очистка)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Optional
from dateparser import parse as parse_date
import json
import re

from bot.gpt.client import ask_gpt
from bot.memory.loader import load_prompt

# Настройка промптов по типам
FORMATTER_PROMPTS = {
    "email": "prompts/email.md",
    "meeting": "prompts/meeting.md",
    "vector": "prompts/vector.md"
}

# Стоп-слова для векторного текста
STOP_WORDS = set([
    "и", "в", "на", "с", "для", "по", "к", "от", "о", "до", "the", "a", "an", "in", "on", "at", "for"
])

# Расширенный словарь для due_at
DATE_LANGUAGES = ["ru", "en"]
DATE_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RELATIVE_BASE": datetime.now()
}


def preprocess_vector_text(text: str) -> str:
    """Очистка текста для vector embeddings: lowercase, убираем стоп-слова и спецсимволы"""
    text = text.lower()
    # удаляем спецсимволы
    text = re.sub(r"[^\w\s]", " ", text)
    # убираем стоп-слова
    words = [w for w in text.split() if w not in STOP_WORDS]
    return " ".join(words)


def parse_due_at(text: Optional[str]) -> int | None:
    """Преобразование текста даты в timestamp с расширенной локализацией"""
    if not text:
        return None
    dt = parse_date(text, languages=DATE_LANGUAGES, settings=DATE_SETTINGS)
    return int(dt.timestamp()) if dt else None


async def format_text(
    raw_text: str,
    fmt_type: str = "email",
    user_id: Optional[int] = None,
    fallback: bool = True
) -> Dict:
    """
    Форматирование текста по типу (email, meeting, vector)
    Использует GPT + fallback
    Возвращает словарь с raw_text + структурированные данные
    """
    prompt_path = FORMATTER_PROMPTS.get(fmt_type)
    result = {"raw_text": raw_text}

    # Загружаем промпт
    try:
        prompt_template = load_prompt(prompt_path)
    except Exception:
        prompt_template = ""

    # Формируем полный промпт для GPT
    full_prompt = f"{prompt_template}\n\nТекст:\n{raw_text}"

    try:
        gpt_response = await ask_gpt(full_prompt)
    except Exception:
        if fallback:
            gpt_response = raw_text
        else:
            raise

    # Обработка результата в зависимости от типа
    try:
        if fmt_type in ["email", "meeting"]:
            gpt_result = json.loads(gpt_response)
        else:
            gpt_result = {"body": gpt_response}
    except Exception:
        # fallback на raw_text
        gpt_result = {"body": raw_text}

    if fmt_type == "email":
        # Парсим due_at
        if "due_at" in gpt_result and gpt_result["due_at"]:
            gpt_result["due_at"] = parse_due_at(gpt_result["due_at"])
        # обязательные поля
        gpt_result.setdefault("subject", None)
        gpt_result.setdefault("to", [])
        gpt_result.setdefault("body", raw_text)
        result.update(gpt_result)

    elif fmt_type == "meeting":
        # tasks и notes
        tasks = gpt_result.get("tasks", [])
        for t in tasks:
            if "due_at" in t:
                t["due_at"] = parse_due_at(t.get("due_at"))
        gpt_result["tasks"] = tasks
        gpt_result.setdefault("notes", [raw_text])
        result.update(gpt_result)

    elif fmt_type == "vector":
        vector_text = preprocess_vector_text(gpt_response)
        result["vector_text"] = vector_text

    else:
        # неизвестный тип
        result["body"] = raw_text

    return result
async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
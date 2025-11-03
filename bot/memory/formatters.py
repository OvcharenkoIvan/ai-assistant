# bot/memory/formatters.py
"""
Formatters: GPT + fallback для нормализации текста и извлечения даты.
Поддерживаемые типы:
- task:  {"body": str, "due_at": epoch|None, "all_day": bool}
- note:  {"body": str}
- email: {"subject": str|None, "to": [str], "body": str, "due_at": epoch|None}
- meeting: {"tasks":[{"task":str,"due_at":epoch|None}], "notes":[str]}
- vector: {"vector_text": str}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Dict, Optional, List

from dateparser import parse as parse_date
from zoneinfo import ZoneInfo

from bot.gpt.client import ask_gpt
from bot.memory.loader import load_prompt
from bot.core.config import TZ

# Имена промптов (без путей и .md) — см. bot/memory/loader.py
FORMATTER_PROMPTS = {
    "task": "task",
    "note": "note",
    "email": "email",
    "meeting": "meeting",
    "vector": "vector",
}

STOP_WORDS = {
    "и", "в", "на", "с", "для", "по", "к", "от", "о", "до",
    "the", "a", "an", "in", "on", "at", "for"
}

def _parse_epoch(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    dt = parse_date(
        text,
        languages=["ru", "en"],
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "TIMEZONE": TZ,
            "RELATIVE_BASE": datetime.now(ZoneInfo(TZ)),
            "PARSERS": ["relative-time", "absolute-time", "timestamp", "custom-formats"],
            "SKIP_TOKENS": ["в", "около", "к", "на"],
        },
    )
    return int(dt.timestamp()) if dt else None

def _detect_all_day(from_text: str) -> bool:
    t = from_text or ""
    if re.search(r"\b(весь день|целый день|день рождения|др|birthday)\b", t, re.IGNORECASE):
        return True
    time_explicit = bool(re.search(r"\b([01]?\d|2[0-3])[:.]\d{2}\b", t)) or bool(
        re.search(r"\bв\s*([01]?\d|2[0-3])\s*час", t, re.IGNORECASE)
    )
    # Если явного времени нет — вероятно all-day
    return not time_explicit

def preprocess_vector_text(text: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (text or "").lower())
    words = [w for w in s.split() if w and w not in STOP_WORDS]
    return " ".join(words)

def _build_messages(sys_prompt: str, user_text: str) -> List[Dict]:
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user",   "content": user_text},
    ]

async def format_text(
    raw_text: str,
    fmt_type: str = "task",
    user_id: Optional[int] = None,
    fallback: bool = True,
) -> Dict:
    """
    Возвращает словарь в зависимости от fmt_type (см. шапку файла).
    Для task/note — стараемся получить компактный body; для task ещё due_at/all_day.
    """
    result: Dict = {"raw_text": raw_text}

    # 1) грузим промпт, если есть
    name = FORMATTER_PROMPTS.get(fmt_type)
    sys_prompt = ""
    if name:
        try:
            sys_prompt = load_prompt(name) or ""
        except Exception:
            sys_prompt = ""

    # 2) если есть промпт — пробуем GPT (строго JSON)
    gpt_obj: Optional[Dict] = None
    if sys_prompt:
        try:
            messages = _build_messages(sys_prompt, raw_text)
            gpt_reply = await ask_gpt(messages)
            # пытаемся распарсить JSON
            gpt_obj = json.loads(gpt_reply)
        except Exception:
            gpt_obj = None

    # 3) Постпроцессинг по типам + fallback
    if fmt_type == "task":
        body = (gpt_obj.get("body") if isinstance(gpt_obj, dict) else None) or raw_text.strip()
        # due_at: сначала из GPT, затем fallback парсером
        due_at_str = (gpt_obj or {}).get("due_at") if isinstance(gpt_obj, dict) else None
        due_at = _parse_epoch(due_at_str) if isinstance(due_at_str, str) else (due_at_str if isinstance(due_at_str, int) else None)
        if due_at is None:
            due_at = _parse_epoch(raw_text)
        all_day = bool((gpt_obj or {}).get("all_day")) if isinstance(gpt_obj, dict) else _detect_all_day(raw_text)
        result.update({"body": body, "due_at": due_at, "all_day": all_day})
        return result

    if fmt_type == "note":
        body = (gpt_obj.get("body") if isinstance(gpt_obj, dict) else None) or raw_text.strip()
        result.update({"body": body})
        return result

    if fmt_type == "email":
        obj = gpt_obj if isinstance(gpt_obj, dict) else {}
        # Нормализация
        subject = obj.get("subject")
        to = obj.get("to") or []
        body = obj.get("body") or raw_text
        due_at = obj.get("due_at")
        if isinstance(due_at, str):
            due_at = _parse_epoch(due_at)
        result.update({"subject": subject, "to": to, "body": body, "due_at": due_at})
        return result

    if fmt_type == "meeting":
        obj = gpt_obj if isinstance(gpt_obj, dict) else {}
        tasks = obj.get("tasks") or []
        norm_tasks = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            txt = t.get("task") or t.get("text") or ""
            da = t.get("due_at")
            if isinstance(da, str):
                da = _parse_epoch(da)
            norm_tasks.append({"task": txt, "due_at": da})
        notes = obj.get("notes") or [raw_text]
        result.update({"tasks": norm_tasks, "notes": notes})
        return result

    if fmt_type == "vector":
        result["vector_text"] = preprocess_vector_text(raw_text)
        return result

    # неизвестный тип — просто вернём тело
    result["body"] = raw_text
    return result

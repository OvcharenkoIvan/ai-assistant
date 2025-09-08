# bot/memory/intent.py
"""
Intent classification: GPT + эвристика + кэширование.
Совместимо с python-telegram-bot v20 и асинхронным SQLite.
"""

from __future__ import annotations
import logging
import re
from telegram import Message
from bot.memory.capture import offer_capture
from bot.gpt.client import ask_gpt

logger = logging.getLogger(__name__)

_intent_cache: dict[str, dict] = {}

# --- триггеры ---
TASK_KEYWORDS = [
    "сделать", "сделай", "нужно", "надо", "запланируй",
    "поставь задачу", "задача", "напомни", "позвони", "купи", "отправь",
    "запиши задачу", "не забудь", "проверь", "встреча", "собрание",
]

NOTE_KEYWORDS = [
    "идея", "заметка", "мысль", "помни", "запиши", "интересно",
    "наблюдение", "в голову пришло", "сохранить", "на подумать",
]

DATE_PATTERNS = [
    r"\bзавтра\b", r"\bсегодня\b", r"\bпослезавтра\b",
    r"\bв понедельник\b", r"\bв \w+ник\b",
    r"\bчерез \d+ (час|дня|дней|минут)\b",
    r"\b\d{1,2}:\d{2}\b",
]

# --- эвристика ---
def classify_intent_heuristic(text: str) -> tuple[str, float]:
    text_l = text.lower()
    score_task, score_note = 0, 0

    for kw in TASK_KEYWORDS:
        if kw in text_l:
            score_task += 1
    for kw in NOTE_KEYWORDS:
        if kw in text_l:
            score_note += 1
    for pattern in DATE_PATTERNS:
        if re.search(pattern, text_l):
            score_task += 2

    if score_task > score_note and score_task > 0:
        return "task", min(1.0, 0.5 + score_task / 5)
    if score_note > score_task and score_note > 0:
        return "note", min(1.0, 0.5 + score_note / 5)
    return "none", 0.0

# --- GPT ---
async def classify_intent_gpt(text: str) -> str:
    """
    Использует GPT Chat API корректно через messages array.
    """
    messages = [
        {"role": "system", "content": "Ты классификатор намерений. Отвечай только task/note/none."},
        {"role": "user", "content": text}
    ]
    result = await ask_gpt(messages)
    return result.strip().lower()

# --- основной метод для бота ---
async def detect_intent(text: str) -> dict:
    # проверка кэша
    cached = _intent_cache.get(text)
    if cached:
        logger.debug("Intent cache hit: %s", cached)
        return cached

    # GPT
    gpt_intent = await classify_intent_gpt(text)
    gpt_conf = 0.7 if gpt_intent != "none" else 0.4

    # эвристика
    heur_intent, heur_conf = classify_intent_heuristic(text)

    # ансамбль
    if heur_intent == gpt_intent and heur_intent != "none":
        confidence = min(1.0, (gpt_conf + heur_conf) / 2 + 0.2)
        result = {"intent": gpt_intent, "confidence": confidence, "source": "gpt+heuristic"}
    elif gpt_intent == "none" and heur_intent != "none" and heur_conf > 0.5:
        result = {"intent": heur_intent, "confidence": heur_conf, "source": "heuristic"}
    else:
        result = {"intent": gpt_intent, "confidence": gpt_conf - 0.2, "source": "gpt"}

    # кэш
    _intent_cache[text] = result
    return result

# --- интеграция с Telegram ---
async def process_intent(message: Message) -> None:
    if not message.text:
        return

    # локальный импорт, чтобы избежать circular import
    from bot.memory.capture import offer_capture

    result = await detect_intent(message.text)
    intent, conf, source = result["intent"], result["confidence"], result["source"]

    logger.info("Intent=%s conf=%.2f source=%s text='%s'", intent, conf, source, message.text)

    if intent in ("task", "note") and conf >= 0.6:
        await offer_capture(message)
    elif intent in ("task", "note") and 0.4 <= conf < 0.6:
        logger.debug("Низкая уверенность, стоит уточнить у пользователя.")
        # Здесь можно реализовать уточнение у пользователя
    else:
        logger.debug("Намерение не распознано или не требуется действие.")  

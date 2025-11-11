# bot/commands/suggest_plan.py
from __future__ import annotations
import logging
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import TZ
from bot.gpt.client import ask_gpt

logger = logging.getLogger(__name__)


def _fmt_epoch(ts: int | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


async def suggest_plan(update: Update, context: ContextTypes.DEFAULT_TYPE, *, _mem) -> None:
    """
    Генерирует краткий план дня и приоритеты на основе текущих задач пользователя.
    """
    if not update.message:
        return
    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    try:
        # Берём только открытые задачи пользователя, максимум 50
        tasks = _mem.list_tasks(user_id=user.id, status="open", limit=50, offset=0)
    except Exception as e:
        logger.exception("suggest_plan: DB error: %s", e)
        await update.message.reply_text("❌ Ошибка: не удалось получить список задач.")
        return

    if not tasks:
        await update.message.reply_text("У тебя пока нет открытых задач. Добавь их командой /task ...")
        return

    # Собираем краткий контекст для GPT
    lines: List[str] = []
    for t in tasks:
        due = _fmt_epoch(getattr(t, "due_at", None))
        lines.append(f"- [{getattr(t, 'id', '?')}] {getattr(t, 'text', '')} (срок: {due})")

    user_prompt = (
        "Сформируй краткий план на сегодня из списка задач. "
        "Определи 3–5 приоритетов, укажи порядок, отметь срочное/важное, предложи переносы, если нужно. "
        "Формат:\n"
        "1) Список приоритетов (коротко)\n"
        "2) Быстрые победы (2–3 пункта)\n"
        "3) Риски/зависимости (если есть)\n"
        "4) Рекомендованные переносы/делегирование (если уместно)\n\n"
        "Мои задачи:\n" + "\n".join(lines)
    )

    messages = [
        {"role": "system", "content": "Ты лаконичный планировщик. Пиши коротко и по делу."},
        {"role": "user", "content": user_prompt},
    ]

    try:
        reply = await ask_gpt(messages)
    except Exception as e:
        logger.exception("suggest_plan: GPT error: %s", e)
        await update.message.reply_text("⚠️ Ошибка GPT при составлении плана.")
        return

    await update.message.reply_text(reply or "Не удалось составить план.")

# bot/gpt/client.py
from __future__ import annotations
import asyncio
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI

from bot.core.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

# Инициализация клиента (если ключ не задан — оставляем None)
_client: Optional[OpenAI] = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class GPTError(RuntimeError):
    """Ошибки обёртки GPT"""
    pass


def is_configured() -> bool:
    """Проверка — настроен ли OpenAI клиент (есть ключ)."""
    return _client is not None


def _ask_gpt_sync(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Синхронный вызов OpenAI SDK.
    Не вызывать прямо из async-кода — используйте async ask_gpt.
    """
    if _client is None:
        raise GPTError("OpenAI API key not configured")

    try:
        resp = _client.chat.completions.create(
            model=model or OPENAI_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else OPENAI_TEMPERATURE,
            max_tokens=max_tokens if max_tokens is not None else OPENAI_MAX_TOKENS,
        )
        # Защитимся на случай нетипичного ответа
        return getattr(resp.choices[0].message, "content", str(resp))
    except Exception as exc:
        logger.exception("GPT sync request failed")
        raise GPTError(str(exc)) from exc


async def ask_gpt(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Асинхронная обёртка для вызова GPT: выполняет блокирующий запрос в threadpool.
    Всегда используйте эту функцию в async-коде: `reply = await ask_gpt(...)`.
    """
    return await asyncio.to_thread(_ask_gpt_sync, messages, model, temperature, max_tokens)

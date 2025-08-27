# bot/memory/intent_cache.py
from __future__ import annotations
import time
import logging
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

# Простой TTL-кэш: key (text) -> (timestamp, value)
_INTENT_CACHE: Dict[str, tuple[float, Any]] = {}
# По умолчанию TTL 1 час. Можно менять из кода при необходимости.
DEFAULT_TTL = 3600.0


def get_cached_intent(text: str) -> Optional[Any]:
    if not text:
        return None
    entry = _INTENT_CACHE.get(text)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > DEFAULT_TTL:
        # устарело — удаляем
        _INTENT_CACHE.pop(text, None)
        logger.debug("Intent cache expired for text: %r", text)
        return None
    logger.debug("Intent cache hit for text: %r", text)
    return value


def set_cached_intent(text: str, value: Any, ttl: Optional[float] = None) -> None:
    if not text:
        return
    _INTENT_CACHE[text] = (time.time(), value)
    logger.debug("Intent cached for text: %r (ttl=%s)", text, ttl or DEFAULT_TTL)


def clear_intent_cache() -> None:
    _INTENT_CACHE.clear()
    logger.info("Intent cache cleared")

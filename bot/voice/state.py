# bot/voice/state.py
from __future__ import annotations

import time
from threading import RLock
from typing import Set, Dict

__all__ = [
    "set_voice_mode",
    "is_voice_on",
    "request_audio",
    "consume_audio_request",
    "should_send_voice_now",
    "clear_audio_request",
    "clear_user_state",
    "debug_state_snapshot",
]

# ==============================
# Константы и внутреннее хранилище
# ==============================

# Сколько секунд держать одноразовый флаг «следующий ответ голосом»
NEXT_AUDIO_TTL_SECONDS = 300  # 5 минут

# Постоянный режим TTS: user_id -> включён/выключен
_user_voice_on: Set[int] = set()

# Одноразовый флаг: user_id -> expires_at (monotonic time)
_next_audio: Dict[int, float] = {}

# Блокировка на случай конкурентных обращений
_lock = RLock()


def _now() -> float:
    """Возвращает текущее монотонное время."""
    return time.monotonic()


def _prune_expired(user_id: int | None = None) -> None:
    """Удаляем протухшие одноразовые флаги."""
    with _lock:
        now = _now()
        if user_id is not None:
            exp = _next_audio.get(user_id)
            if exp is not None and exp <= now:
                _next_audio.pop(user_id, None)
            return

        # Полная чистка (редко вызывается)
        to_del = [uid for uid, exp in _next_audio.items() if exp <= now]
        for uid in to_del:
            _next_audio.pop(uid, None)


# ==============================
# Публичный API
# ==============================

def set_voice_mode(user_id: int, enabled: bool) -> None:
    """
    Включает/выключает постоянный голосовой режим для пользователя.
    При enabled=True ответы дублируются в аудио всегда.
    """
    with _lock:
        if enabled:
            _user_voice_on.add(user_id)
        else:
            _user_voice_on.discard(user_id)


def is_voice_on(user_id: int) -> bool:
    """Проверяет, включён ли постоянный голосовой режим."""
    with _lock:
        return user_id in _user_voice_on


def request_audio(user_id: int, ttl_seconds: int | None = None) -> None:
    """
    Запрашивает голос ТОЛЬКО для следующего ответа.
    Флаг сам протухает через ttl_seconds (по умолчанию NEXT_AUDIO_TTL_SECONDS).
    """
    ttl = ttl_seconds if ttl_seconds is not None else NEXT_AUDIO_TTL_SECONDS
    expires_at = _now() + max(1, ttl)  # защита от нулевого/отрицательного TTL
    with _lock:
        _next_audio[user_id] = expires_at


def consume_audio_request(user_id: int) -> bool:
    """
    Проверяет, запрошен ли одноразовый голосовой ответ.
    Если запрошен и флаг не протух — возвращает True и СБРАСЫВАЕТ флаг.
    Если нет — False.
    """
    with _lock:
        _prune_expired(user_id)
        if user_id in _next_audio:
            _next_audio.pop(user_id, None)
            return True
        return False


def should_send_voice_now(user_id: int) -> bool:
    """
    Удобный метод для места отправки ответа:
    - Если включён постоянный режим → True (флаг одноразового не трогаем).
    - Иначе пытаемся «съесть» одноразовый флаг → True/False.
    """
    if is_voice_on(user_id):
        return True
    return consume_audio_request(user_id)


def clear_audio_request(user_id: int) -> None:
    """
    Сбрасывает одноразовый флаг «следующий ответ голосом»,
    чтобы следующий ответ был текстом.
    """
    with _lock:
        _next_audio.pop(user_id, None)


def clear_user_state(user_id: int) -> None:
    """
    Полностью очищает состояние пользователя (и постоянный, и одноразовый режимы).
    """
    with _lock:
        _user_voice_on.discard(user_id)
        _next_audio.pop(user_id, None)


def debug_state_snapshot() -> dict:
    """
    Возвращает снимок состояния (для отладки/логов).
    Не использовать для пользовательского вывода.
    """
    with _lock:
        return {
            "voice_on_users": list(_user_voice_on),
            "next_audio_users": [
                {"user_id": uid, "expires_in": max(0, _next_audio[uid] - _now())}
                for uid in _next_audio
            ],
            "ttl_default": NEXT_AUDIO_TTL_SECONDS,
        }

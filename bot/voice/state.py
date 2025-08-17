# bot/voice/state.py
from typing import Set

# Простая in-memory карта. Позже легко вынести в SQLite.
_user_voice_on: Set[int] = set()

def set_voice_mode(user_id: int, enabled: bool) -> None:
    if enabled:
        _user_voice_on.add(user_id)
    else:
        _user_voice_on.discard(user_id)

def is_voice_on(user_id: int) -> bool:
    return user_id in _user_voice_on

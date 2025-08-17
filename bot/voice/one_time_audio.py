# bot/voice/one_time_audio.py
from typing import Set

# пользователи, которые попросили аудио в следующем ответе
_one_time_audio: Set[int] = set()

def request_audio(user_id: int) -> None:
    """Пометить, что пользователь хочет аудио в следующем ответе"""
    _one_time_audio.add(user_id)

def pop_audio_request(user_id: int) -> bool:
    """Проверить и снять флаг одноразового аудио"""
    if user_id in _one_time_audio:
        _one_time_audio.discard(user_id)
        return True
    return False

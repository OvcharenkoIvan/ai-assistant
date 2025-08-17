# bot/voice/stt.py
import asyncio
import logging
from pathlib import Path
from openai import OpenAI

from bot.core.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client = None
def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY не настроен")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client

def _transcribe_sync(file_path: str) -> str:
    """
    Блокирующий вызов OpenAI Whisper API. Оборачиваем его в поток в асинхронной обёртке.
    """
    client = _get_client()
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Файл для распознавания не найден: {file_path}")

    with p.open("rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            # Можно явно указать язык, если знаешь:
            # language="ru"
        )
    text = getattr(resp, "text", "") or ""
    return text.strip()

async def transcribe(file_path: str) -> str:
    """
    Асинхронная обёртка. Не блокирует event loop.
    """
    try:
        return await asyncio.to_thread(_transcribe_sync, file_path)
    except Exception as e:
        logger.exception("Ошибка распознавания речи Whisper")
        raise RuntimeError(f"Ошибка STT: {e}") from e

# bot/voice/tts.py
import re
import asyncio
import logging
from pathlib import Path
from gtts import gTTS

logger = logging.getLogger(__name__)

_LANG_RU = "ru"
_LANG_EN = "en"

# Простая эвристика: если в тексте есть заметная доля латиницы — берём EN, иначе RU
_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRIL_RE = re.compile(r"[А-Яа-яЁё]")

def pick_lang(text: str) -> str:
    latin = len(_LATIN_RE.findall(text or ""))
    cyril = len(_CYRIL_RE.findall(text or ""))
    if latin > cyril:
        return _LANG_EN
    return _LANG_RU

def _speak_sync(text: str, out_path: str, lang: str | None = None) -> str:
    if not text:
        text = "Пустой ответ."
    lang = lang or pick_lang(text)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tts = gTTS(text=text, lang=lang)
    tts.save(out.as_posix())
    return out.as_posix()

async def speak(text: str, out_path: str, lang: str | None = None) -> str:
    """
    Генерирует MP3 с озвучкой. Возвращает путь к файлу.
    """
    try:
        return await asyncio.to_thread(_speak_sync, text, out_path, lang)
    except Exception as e:
        logger.exception("Ошибка TTS (gTTS)")
        raise RuntimeError(f"Ошибка TTS: {e}") from e

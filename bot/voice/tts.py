# bot/voice/tts.py
import re
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from gtts import gTTS

from bot.core.config import UPLOADS_DIR
from bot.voice.state import clear_audio_request

logger = logging.getLogger(__name__)

_LANG_RU = "ru"
_LANG_EN = "en"

_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRIL_RE = re.compile(r"[А-Яа-яЁё]")

def pick_lang(text: str) -> str:
    latin = len(_LATIN_RE.findall(text or ""))
    cyril = len(_CYRIL_RE.findall(text or ""))
    return _LANG_EN if latin > cyril else _LANG_RU

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
    """Генерирует MP3 с озвучкой. Возвращает путь к файлу."""
    try:
        return await asyncio.to_thread(_speak_sync, text, out_path, lang)
    except Exception as e:
        logger.exception("Ошибка TTS (gTTS)")
        raise RuntimeError(f"Ошибка TTS: {e}") from e

async def synthesize_and_send_voice(update, text: str):
    """Генерация аудио и отправка в Telegram, с учётом одноразового флага."""
    try:
        user_id = update.effective_user.id
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_dir = Path(UPLOADS_DIR) / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        mp3_path = user_dir / f"{ts}_reply.mp3"

        # Генерация аудио
        await speak(text, mp3_path.as_posix())

        # Отправка в Telegram
        with mp3_path.open("rb") as f:
            await update.message.reply_audio(
                audio=f,
                caption="🔊 Аудио-ответ",
                title=f"reply_{ts}.mp3",
            )
    except Exception as e:
        logger.exception("Ошибка при генерации/отправке аудио")
    finally:
        # Сбрасываем одноразовый флаг, если он был
        clear_audio_request(user_id)

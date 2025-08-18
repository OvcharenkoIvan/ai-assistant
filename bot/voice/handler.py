# bot/voice/handler.py
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import UPLOADS_DIR
from bot.voice.stt import transcribe
from bot.voice.tts import synthesize_and_send_voice  # единая точка TTS
from bot.voice.state import should_send_voice_now
from bot.gpt.chat import build_messages, ask_gpt

logger = logging.getLogger(__name__)


async def _ogg_to_mp3(ogg_path: str, mp3_path: str) -> None:
    """Конвертация OGG(Opus) -> MP3 через ffmpeg в отдельном потоке."""
    import subprocess

    cmd = [
        "ffmpeg",
        "-y",
        "-i", ogg_path,
        "-acodec", "libmp3lame",
        "-ar", "44100",
        mp3_path,
    ]
    proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {proc.stderr}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка голосового сообщения:
    1) Скачиваем voice.ogg
    2) Конвертируем в MP3
    3) STT -> текст
    4) GPT -> ответ
    5) Отправляем текст (и аудио, если голосовой режим включён или одноразовый флаг)
    """
    if not update.message or not update.message.voice:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name

    # Пути для пользователя
    user_dir = Path(UPLOADS_DIR) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ogg_path = user_dir / f"{ts}_input.ogg"
    mp3_in_path = user_dir / f"{ts}_input.mp3"

    try:
        # 1) Скачивание .ogg
        voice_file = await update.message.voice.get_file()
        await voice_file.download_to_drive(ogg_path.as_posix())
        logger.info(f"[voice] {username} -> сохранён {ogg_path.name}")

        # 2) Конвертация в MP3
        await _ogg_to_mp3(ogg_path.as_posix(), mp3_in_path.as_posix())

        # 3) STT
        recognized_text = await transcribe(mp3_in_path.as_posix())
        if not recognized_text:
            recognized_text = "(не удалось распознать речь)"
        logger.info(f"[voice->text] {username}: {recognized_text}")

        # 4) GPT
        messages = build_messages(user_id, recognized_text)
        reply_text = ask_gpt(messages).strip()

        # 5) Отправка текста
        await update.message.reply_text(
            f"🗣 Ты сказал: {recognized_text}\n\n💬 Ответ: {reply_text}"
        )

        # 6) Отправка TTS (глобально включено или одноразовый флаг)
        if should_send_voice_now(user_id):
            await synthesize_and_send_voice(update, reply_text)

    except Exception as e:
        logger.exception("Ошибка при обработке голосового сообщения")
        await update.message.reply_text(f"⚠️ Ошибка обработки голосового сообщения: {e}")

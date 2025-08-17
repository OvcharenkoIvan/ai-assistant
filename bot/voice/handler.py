# bot/voice/handler.py
import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot.core.config import UPLOADS_DIR
from bot.voice.stt import transcribe
from bot.voice.tts import speak
from bot.voice.state import is_voice_on
from bot.gpt.chat import build_messages, ask_gpt

logger = logging.getLogger(__name__)

def _ffmpeg_convert_sync(src_path: str, dst_path: str) -> str:
    """
    Конвертация OGG(Opus) -> MP3 через ffmpeg.
    -y: перезаписывать без вопросов
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", src_path,
        "-acodec", "libmp3lame",
        "-ar", "44100",
        dst_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {proc.stderr}")
    return dst_path

async def _ogg_to_mp3(ogg_path: str, mp3_path: str) -> str:
    return await asyncio.to_thread(_ffmpeg_convert_sync, ogg_path, mp3_path)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    1) Скачиваем voice.ogg
    2) Конвертируем в .mp3
    3) STT -> текст
    4) GPT -> ответ
    5) Отправляем текст (+ аудио, если голосовой режим включён)
    """
    if not update.message or not update.message.voice:
        return

    user = update.effective_user
    user_id = user.id
    username = user.username or user.full_name

    # Пути для пользователя
    user_dir = Path(UPLOADS_DIR) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ogg_path = user_dir / f"{ts}_input.ogg"
    mp3_in_path = user_dir / f"{ts}_input.mp3"
    mp3_out_path = user_dir / f"{ts}_reply.mp3"

    try:
        # 1) Скачивание .ogg
        file = await update.message.voice.get_file()
        await file.download_to_drive(ogg_path.as_posix())
        logger.info(f"[voice] {username} -> сохранён {ogg_path.name}")

        # 2) Конвертация в .mp3
        await _ogg_to_mp3(ogg_path.as_posix(), mp3_in_path.as_posix())

        # 3) STT
        recognized_text = await transcribe(mp3_in_path.as_posix())
        if not recognized_text:
            recognized_text = "(не удалось распознать речь)"
        logger.info(f"[voice->text] {username}: {recognized_text}")

        # 4) GPT
        messages = build_messages(user_id, recognized_text)
        reply_text = ask_gpt(messages).strip()

        # 5) Ответ: всегда текст
        await update.message.reply_text(
            f"🗣 Ты сказал: {recognized_text}\n\n💬 Ответ: {reply_text}"
        )

        # Если голосовой режим включён — озвучиваем ответ и отправляем mp3 как аудио
        if is_voice_on(user_id):
            await speak(reply_text, mp3_out_path.as_posix())
            with mp3_out_path.open("rb") as f:
                await update.message.reply_audio(
                    audio=f,
                    caption="🔊 Аудио-ответ",
                    title=f"reply_{ts}.mp3",
                )

    except Exception as e:
        logger.exception("Ошибка при обработке голосового сообщения")
        await update.message.reply_text(f"⚠️ Ошибка обработки голосового сообщения: {e}")

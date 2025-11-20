# bot/core/secure_tokens.py
from __future__ import annotations

"""
Примитивы для безопасного хранения чувствительных данных (например, OAuth-токенов).

Использование:
- encrypt_dict / decrypt_dict — для JSON-словарей (token_json в oauth_tokens)
- encrypt_text / decrypt_text — для произвольных строк (на будущее)
"""

import json
import logging
import os
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_FERNET: Fernet | None = None


def _get_fernet() -> Fernet:
    """
    Возвращает singleton Fernet, инициализированный по ENCRYPTION_KEY из окружения.

    Требования к ключу:
      - ENCRYPTION_KEY должен быть результатом Fernet.generate_key().decode(),
        то есть base64-строка длиной 44 символа.
    """
    global _FERNET
    if _FERNET is not None:
        return _FERNET

    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY не задан. Невозможно инициализировать шифрование токенов."
        )

    # Небольшая проверка формата (чисто для более понятной ошибки)
    if len(key) < 32:
        raise RuntimeError(
            "ENCRYPTION_KEY выглядит подозрительно коротким. "
            "Сгенерируй его через Fernet.generate_key()."
        )

    try:
        _FERNET = Fernet(key.encode("utf-8"))
    except Exception:
        logger.exception("Не удалось инициализировать Fernet. Проверь ENCRYPTION_KEY в .env")
        raise RuntimeError("ENCRYPTION_KEY некорректен, не удалось инициализировать Fernet")

    return _FERNET


def encrypt_dict(data: Dict[str, Any]) -> str:
    """
    Сериализует dict -> JSON -> шифрует через Fernet -> str (base64).
    Используем для token_json в oauth_tokens.
    """
    f = _get_fernet()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = f.encrypt(blob)
    return token.decode("utf-8")


def decrypt_dict(blob: str) -> Dict[str, Any]:
    """
    Расшифровывает str (как из БД) -> dict.

    Backward-compatible логика:
      1) Пробуем как Fernet-шифротекст
      2) Если InvalidToken — пробуем воспринять как старый plaintext JSON
    """
    if not blob:
        return {}

    f = _get_fernet()

    try:
        # Пытаемся расшифровать как Fernet-токен
        decrypted = f.decrypt(blob.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except InvalidToken:
        # Скорее всего, это старый JSON без шифрования
        try:
            return json.loads(blob)
        except Exception:
            logger.exception(
                "decrypt_dict: строка не расшифровывается и не парсится как JSON. blob (обрезан): %r",
                blob[:80],
            )
            raise
    except Exception:
        logger.exception("decrypt_dict: общая ошибка при расшифровке токена")
        raise


def encrypt_text(text: str) -> str:
    """
    Шифрование произвольной текстовой строки.
    На будущее — если захочешь шифровать ещё что-то (не только JSON).
    """
    f = _get_fernet()
    return f.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    f = _get_fernet()
    return f.decrypt(token.encode("utf-8")).decode("utf-8")

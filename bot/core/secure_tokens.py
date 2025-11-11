# bot/core/secure_tokens.py

# --- Auto-load .env ---
from pathlib import Path
import os
try:
    from dotenv import load_dotenv
    ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_FERNET: Optional[Fernet] = None

def _get_fernet() -> Optional[Fernet]:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        logger.warning("ENCRYPTION_KEY is not set; tokens will be stored in plaintext.")
        _FERNET = None
        return None
    try:
        _FERNET = Fernet(key.encode("utf-8"))
        return _FERNET
    except Exception as e:
        logger.error("Invalid ENCRYPTION_KEY: %s", e)
        _FERNET = None
        return None

def encrypt_json(obj: Dict[str, Any]) -> str:
    """
    Возвращает str (base64-фернет) или JSON-string (если ключа нет).
    """
    try:
        f = _get_fernet()
        blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        if f is None:
            # нет ключа — храним как обычный JSON
            return blob.decode("utf-8")
        token = f.encrypt(blob)
        return token.decode("utf-8")
    except Exception as e:
        logger.exception("encrypt_json failed, fallback to plaintext: %s", e)
        return json.dumps(obj, ensure_ascii=False)

def decrypt_json(s: str) -> Dict[str, Any]:
    """
    Принимает str (фернет-шифротекст или обычный JSON). Возвращает dict.
    """
    if not s:
        return {}
    f = _get_fernet()
    # Сначала пробуем как шифротекст:
    if f is not None:
        try:
            data = f.decrypt(s.encode("utf-8"))
            return json.loads(data.decode("utf-8"))
        except InvalidToken:
            # не шифровали — это обычный JSON
            pass
        except Exception:
            # иное — попробуем JSON
            pass
    # Пытаемся распарсить как JSON
    try:
        return json.loads(s)
    except Exception:
        logger.error("decrypt_json: cannot parse token, returning empty dict")
        return {}

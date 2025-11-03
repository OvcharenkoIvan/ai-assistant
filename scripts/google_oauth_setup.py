# scripts/google_oauth_setup.py
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Dict

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# --- Поднимаем import пути проекта ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.core.config import (
    DB_PATH,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_OAUTH_SCOPES,
)
from bot.memory.memory_sqlite import MemorySQLite

def main() -> None:
    parser = argparse.ArgumentParser(description="One-time Google OAuth provisioning for personal assistant")
    parser.add_argument("--user-id", type=int, required=True, help="Telegram user_id владельца (например, 423368779)")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Путь к SQLite БД (по умолчанию из config.DB_PATH)")
    parser.add_argument("--redirect-uri", type=str, default=GOOGLE_REDIRECT_URI, help="Redirect URI (например, http://localhost:8765/)")
    parser.add_argument("--scopes", type=str, nargs="*", default=GOOGLE_OAUTH_SCOPES, help="OAuth scopes")
    args = parser.parse_args()

    client_config = {
        "installed": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [args.redirect_uri],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=args.scopes)
    # Откроет браузер и поднимет локальный HTTP на указанном порту из redirect-uri
    creds: Credentials = flow.run_local_server(
        host="localhost",
        port=int(args.redirect_uri.split(":")[-1].rstrip("/")),
        authorization_prompt_message="Откройте ссылку, выберите аккаунт Google и подтвердите доступ к календарю.",
        success_message="Готово! Возвращайтесь в терминал — токен сейчас будет сохранён.",
        open_browser=True,
    )

    token_dict: Dict[str, Any] = {
        "token": creds.token,
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
    }

    db = MemorySQLite(args.db)
    db.upsert_oauth_token(
        user_id=str(args.user_id),
        provider="google_calendar",
        token_json=token_dict,
        expiry=token_dict.get("expiry"),
        scopes=creds.scopes,
    )

    stored = db.get_oauth_token(str(args.user_id), "google_calendar")
    if not stored:
        raise SystemExit("❌ Ошибка: токен не сохранился в oauth_tokens")

    print(f"✅ Google Calendar подключён. user_id={args.user_id}")
    print(f"   БД: {args.db}")
    print("   Теперь можно запускать бота — календарь доступен без дополнительных действий.")

if __name__ == "__main__":
    main()

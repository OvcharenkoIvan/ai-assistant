# bot/core/config.py
from __future__ import annotations

from pathlib import Path
import os
from dotenv import load_dotenv

# --- Корень проекта и .env ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

# --- Ключи/токены (существующие) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN не найден в .env")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
AUTO_WEB = int(os.getenv("AUTO_WEB", 1))
SEARCH_LOCALE = os.getenv("SEARCH_LOCALE", "ru")
SEARCH_COUNTRY = os.getenv("SEARCH_COUNTRY", "US")

# --- Директории (существующие) ---
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
UPLOADS_DIR = DATA_DIR / "uploads"
for p in (DATA_DIR, LOG_DIR, UPLOADS_DIR):
    p.mkdir(parents=True, exist_ok=True)

# --- Настройки GPT (существующие) ---
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "700"))

# --- Таймзона (существующая) ---
TZ = os.getenv("TZ", "Europe/Warsaw")

# =====================================================================
#                         GOOGLE CALENDAR (НОВОЕ)
# =====================================================================

# 1) Путь к БД (единая точка правды для всех модулей)
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "app.sqlite3"))

# 2) OAuth-клиент для офлайн-provisioning (InstalledApp + локальный redirect)
#    Смотри scripts/google_oauth_setup.py — токен кладётся в таблицу oauth_tokens,
#    после чего Telegram/бот работают без дополнительных авторизаций в чате.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Для локального сценария provisioning используем http://localhost:8765/
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8765/")

# 3) Scopes — по умолчанию: создание/редактирование событий и чтение
GOOGLE_OAUTH_SCOPES = (
    os.getenv(
        "GOOGLE_OAUTH_SCOPES",
        "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly",
    )
    .strip()
    .split()
)

# 4) Календарь по умолчанию (обычно "primary")
GOOGLE_DEFAULT_CALENDAR_ID = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID", "primary")

# 5) Окно синхронизации и период (минуты) — для планировщика APScheduler
SYNC_WINDOW_DAYS = int(os.getenv("SYNC_WINDOW_DAYS", "30"))          # сколько дней назад/вперёд тянуть
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))  # периодический sync

# --- Валидация критически важных переменных для календаря ---
# Если в проде нет client_id/secret — лучше упасть сразу, чем ловить неявные ошибки.
# Для локальной разработки можно временно закомментировать.
if os.getenv("ENV", "dev") == "prod":
    if not GOOGLE_CLIENT_ID:
        raise RuntimeError("❌ GOOGLE_CLIENT_ID не найден в .env")
    if not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("❌ GOOGLE_CLIENT_SECRET не найден в .env")
# End of config.py
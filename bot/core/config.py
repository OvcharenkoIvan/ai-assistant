# bot/core/config.py
from __future__ import annotations

from pathlib import Path
import os
from dotenv import load_dotenv

# --- Корень проекта и .env ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

# --- Общие директории ---
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
UPLOADS_DIR = DATA_DIR / "uploads"
for p in (DATA_DIR, LOG_DIR, UPLOADS_DIR):
    p.mkdir(parents=True, exist_ok=True)

# --- Базовые ключи/модели ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "700"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN не найден в .env")

# --- Веб-поиск (если используешь) ---
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
AUTO_WEB = int(os.getenv("AUTO_WEB", 1))
SEARCH_LOCALE = os.getenv("SEARCH_LOCALE", "ru")
SEARCH_COUNTRY = os.getenv("SEARCH_COUNTRY", "US")

# --- Таймзона и логирование ---
TZ = os.getenv("TZ", "Europe/Warsaw")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Tenant / Owner ---
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "default")

# --- Пути к БД (per-tenant) ---
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "app.sqlite3"))

# Jobstore: отдельная SQLite для APScheduler
JOBSTORE_DB_PATH = os.getenv("JOBSTORE_DB_PATH", str(DATA_DIR / "jobs.sqlite3"))

# --- Google Calendar (офлайн-provisioning уже сделан) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8765/")
GOOGLE_OAUTH_SCOPES = (
    os.getenv(
        "GOOGLE_OAUTH_SCOPES",
        "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly",
    ).strip().split()
)
GOOGLE_DEFAULT_CALENDAR_ID = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID", "primary")

# Окно синка и интервал
SYNC_WINDOW_DAYS = int(os.getenv("SYNC_WINDOW_DAYS", "30"))
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))

# --- Бэкап ---
BACKUP_ENABLED = int(os.getenv("BACKUP_ENABLED", "1"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(DATA_DIR / "backups")))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_TIME = os.getenv("BACKUP_TIME", "02:30")  # HH:MM локальное
BACKUP_KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "14"))

# --- Валидация в проде ---
if os.getenv("ENV", "dev") == "prod":
    if not GOOGLE_CLIENT_ID:
        raise RuntimeError("❌ GOOGLE_CLIENT_ID не найден в .env")
    if not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("❌ GOOGLE_CLIENT_SECRET не найден в .env")
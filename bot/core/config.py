from pathlib import Path
import os
from dotenv import load_dotenv

# --- Корень проекта и .env ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

# --- Ключи/токены ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN не найден в .env")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")    
AUTO_WEB = int(os.getenv("AUTO_WEB", 1)) 
SEARCH_LOCALE = os.getenv("SEARCH_LOCALE", "ru") 
SEARCH_COUNTRY = os.getenv("SEARCH_COUNTRY", "US")

# --- Директории ---
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
UPLOADS_DIR = DATA_DIR / "uploads"
for p in (DATA_DIR, LOG_DIR, UPLOADS_DIR):
    p.mkdir(parents=True, exist_ok=True)

# --- Настройки GPT ---
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "700"))

# --- Таймзона ---
TZ = os.getenv("TZ", "Europe/Warsaw")

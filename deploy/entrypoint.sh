#!/bin/bash
set -e

echo "🚀 Starting AI Assistant instance: $INSTANCE_NAME"
echo "🕒 Timezone: $TZ"

# Инициализация директорий
mkdir -p /app/data/db /app/data/backups

# Проверка наличия БД
if [ ! -f "$DB_PATH" ]; then
  echo "📁 Creating new SQLite database at $DB_PATH"
  python - <<'PY'
from bot.memory.memory_sqlite import MemorySQLite
import os
os.makedirs(os.path.dirname(os.environ.get("DB_PATH", "/app/data/db/app.sqlite3")), exist_ok=True)
MemorySQLite(os.environ.get("DB_PATH", "/app/data/db/app.sqlite3"))
print("✅ Database initialized.")
PY
fi

# Запуск бота
exec python -m bot.main
# -------- End of entrypoint.sh --------
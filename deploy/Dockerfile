# -------- Dockerfile --------
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata curl git sqlite3 \
 && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости проекта
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY bot/ bot/
COPY tools/ tools/
COPY scripts/ scripts/
COPY deploy/entrypoint.sh .

# Создаём каталоги для данных и бэкапов
RUN mkdir -p /app/data/db /app/data/backups

# Разрешения
RUN chmod +x /app/entrypoint.sh

# Задаём рабочую директорию и команду
WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "bot"]
# -------- End of Dockerfile --------
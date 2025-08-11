import logging
import os
from datetime import datetime

# Папка для логов
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Путь к файлу логов
log_file = os.path.join(LOG_DIR, "actions.log")

# Настройка логирования
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

def log_action(action: str):
    """
    Записывает действие в лог-файл и выводит его в консоль
    """
    logging.info(action)
    print(f"[LOG] {datetime.now()} - {action}")

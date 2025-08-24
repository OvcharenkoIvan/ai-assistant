# bot/memory/loader.py
from __future__ import annotations
import os
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Определяем корень проекта (папка выше /bot)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROMPTS_DIR = os.path.join(PROJECT_ROOT, "prompts")

# Кэш: имя -> (mtime файла, содержимое)
_cache: Dict[str, Tuple[float, str]] = {}

def load_prompt(name: str) -> str:
    """
    Загружает промпт из prompts/<name>.md.
    - Использует кэш, чтобы не читать файл каждый раз.
    - Если файл изменился — перечитывает его.
    - Если файл отсутствует или ошибка — возвращает пустую строку.
    """
    path = os.path.join(PROMPTS_DIR, f"{name}.md")
    try:
        mtime = os.path.getmtime(path)
        # проверяем кэш
        cached = _cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]

        # читаем файл
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        # сохраняем в кэш
        _cache[name] = (mtime, content)
        return content

    except FileNotFoundError:
        logger.warning("Файл промпта %s не найден", path)
    except Exception as e:
        logger.error("Ошибка при чтении промпта %s: %s", path, e)
    return ""

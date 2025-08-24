from __future__ import annotations
import logging

try:
    from bot.memory.loader import load_prompt
except Exception:
    def load_prompt(name: str) -> str:
        return ""

logger = logging.getLogger(__name__)

# Безопасные дефолты
_DEFAULT_CORE = (
    "Ты персональный ассистент. Отвечай кратко и по делу. "
    "Если ссылаешься на внешние источники — укажи их. Не выдумывай факты."
)
_DEFAULT_TASKS = (
    "Роль: менеджер задач. Помогай формулировать чёткие next-step задачи. "
    "Структура: краткое название + уточнение (если нужно). "
    "Если пользователь назвал срок — зафиксируй его. Не придумывай сроки от себя."
)
_DEFAULT_NOTES = (
    "Роль: хранитель заметок и идей. Помогай аккуратно формулировать мысли, "
    "но не переписывай смысл. Не добавляй лишних фактов."
)

def _safe(name: str, default: str) -> str:
    txt = (load_prompt(name) or "").strip()
    if not txt:
        logger.info("Prompt %s.md не найден или пустой — использую дефолт.", name)
        return default
    return txt

def get_core_prompt() -> str:
    return _safe("core", _DEFAULT_CORE)

def get_tasks_prompt() -> str:
    return _safe("tasks", _DEFAULT_TASKS)

def get_notes_prompt() -> str:
    return _safe("notes", _DEFAULT_NOTES)

def get_full_prompt() -> str:
    """Объединяет все промты в один текст для системного промта GPT"""
    parts = [
        get_core_prompt(),
        "",
        "=== Задачи ===",
        get_tasks_prompt(),
        "",
        "=== Заметки ===",
        get_notes_prompt(),
    ]
    return "\n".join(parts)

# Удобный системный промт для chat.py
SYSTEM_PROMPT = get_core_prompt()
# Полный промт для memory.py
FULL_PROMPT = get_full_prompt() 
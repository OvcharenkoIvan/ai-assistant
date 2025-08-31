# bot/memory/memory_loader.py
from __future__ import annotations
import os
import logging
from typing import Optional
import asyncio  # добавлен импорт для запуска корутины

from .memory_base import MemoryBackend
from . import memory_inmemory as inm
from . import memory_sqlite as sql  # существующий модуль с SQLite-функциями

logger = logging.getLogger(__name__)

# Singleton instance
_MEMORY_INSTANCE: Optional[MemoryBackend] = None

class _SQLiteAdapter(MemoryBackend):
    """
    Адаптер MemoryBackend поверх существующего procedural memory_sqlite.py.
    Не изменяет существующие функции — вызывает их напрямую.
    """

    def __init__(self) -> None:
        # Корректный запуск асинхронной инициализации
        asyncio.run(sql.init_db())
        logger.info("SQLiteAdapter initialized (DB path: %s)", getattr(sql, "_DB_PATH", "unknown"))

    def init(self) -> None:
        # DB уже инициализирован в __init__
        return

    def add_task(self, text: str, user_id: Optional[int] = None, due_at: Optional[int] = None) -> int:
        return sql.add_task(text=text, user_id=user_id, due_at=due_at)

    def add_note(self, text: str, user_id: Optional[int] = None) -> int:
        return sql.add_note(text=text, user_id=user_id)

    def list_tasks(self, user_id: Optional[int] = None, status: Optional[str] = None,
                   limit: Optional[int] = 100, offset: int = 0):
        return sql.list_tasks(user_id=user_id, status=status, limit=limit, offset=offset)

    def list_notes(self, user_id: Optional[int] = None, limit: Optional[int] = 100, offset: int = 0):
        return sql.list_notes(user_id=user_id, limit=limit, offset=offset)

    def get_task(self, task_id: int):
        return sql.get_task(task_id)

    def get_note(self, note_id: int):
        return sql.get_note(note_id)

    def update_task_status(self, task_id: int, status: str) -> bool:
        return sql.update_task_status(task_id, status)

    def delete_task(self, task_id: int) -> bool:
        return sql.delete_task(task_id)

    def delete_note(self, note_id: int) -> bool:
        return sql.delete_note(note_id)

# --- Получение singleton-инстанса ---
def get_memory(backend: Optional[str] = None) -> MemoryBackend:
    """
    Возвращает singleton MemoryBackend.
    backend: 'sqlite' | 'inmemory' — если не указан, берётся из ENV MEMORY_BACKEND
    """
    global _MEMORY_INSTANCE
    if _MEMORY_INSTANCE is not None:
        return _MEMORY_INSTANCE

    choice = (backend or os.getenv("MEMORY_BACKEND", "sqlite")).lower()
    if choice == "sqlite":
        _MEMORY_INSTANCE = _SQLiteAdapter()
    elif choice in ("inmemory", "memory_inmemory", "memory-inmemory"):
        mem = inm.InMemoryMemory()
        mem.init()
        _MEMORY_INSTANCE = mem
    else:
        raise RuntimeError(f"Unknown MEMORY_BACKEND='{choice}' (supported: sqlite, inmemory)")

    logger.info("MemoryLoader: backend=%s", choice)
    return _MEMORY_INSTANCE

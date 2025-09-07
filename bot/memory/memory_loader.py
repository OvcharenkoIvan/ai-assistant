# bot/memory/memory_loader.py
from __future__ import annotations
import os
import logging
from typing import Optional
from .memory_sqlite import MemorySQLite
from .memory_base import MemoryBackend
from . import memory_inmemory as inm

logger = logging.getLogger(__name__)

# Singleton instance
_MEMORY_INSTANCE: Optional[MemoryBackend] = None

class _SQLiteAdapter(MemoryBackend):
    """
    Адаптер MemoryBackend поверх MemorySQLite.
    Сохраняет один экземпляр MemorySQLite для всего бота.
    Поддерживает raw_text и extra, чтобы capture.py работал корректно.
    """

    def __init__(self) -> None:
        # создаём один экземпляр класса MemorySQLite
        self._sqlite = MemorySQLite()
        logger.info("SQLiteAdapter initialized (DB path: %s)", self._sqlite.db_path)

    def init(self) -> None:
        # DB уже инициализирован в __init__
        return

    # --- Задачи ---
    def add_task(
        self,
        text: str,
        user_id: Optional[int] = None,
        *,
        raw_text: Optional[str] = None,
        due_at: Optional[int] = None,
        extra: Optional[dict] = None
    ) -> int:
        return self._sqlite.add_task(
            user_id=user_id or 0,
            text=text,
            raw_text=raw_text,
            due_at=due_at,
            extra=extra,
        )

    def get_task(self, task_id: int):
        return self._sqlite.get_task(task_id)

    def list_tasks(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ):
        return self._sqlite.list_tasks(user_id=user_id, status=status, limit=limit, offset=offset)

    def update_task_status(self, task_id: int, status: str) -> bool:
        return self._sqlite.update_task(task_id, status=status)

    def delete_task(self, task_id: int) -> bool:
        return self._sqlite.delete_task(task_id)

    # --- Заметки ---
    def add_note(
        self,
        text: str,
        user_id: Optional[int] = None,
        *,
        raw_text: Optional[str] = None,
        extra: Optional[dict] = None
    ) -> int:
        return self._sqlite.add_note(
            user_id=user_id or 0,
            text=text,
            raw_text=raw_text,
            extra=extra,
        )

    def get_note(self, note_id: int):
        return self._sqlite.get_note(note_id)

    def list_notes(
        self,
        user_id: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ):
        return self._sqlite.list_notes(user_id=user_id, limit=limit, offset=offset)

    def delete_note(self, note_id: int) -> bool:
        return self._sqlite.delete_note(note_id)


def get_memory(backend: Optional[str] = None) -> MemoryBackend:
    """
    Возвращает singleton MemoryBackend для всего бота.
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

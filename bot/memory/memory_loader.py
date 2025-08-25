# bot/memory/memory_loader.py
from __future__ import annotations
import os
import logging
from typing import Optional, List, Protocol, Any

from . import memory_inmemory as inm
from . import memory_sqlite as sql  # procedural SQLite backend

logger = logging.getLogger(__name__)

# ---- Интерфейс памяти ----
class MemoryBackend(Protocol):
    """Единый интерфейс для всех реализаций памяти."""

    def init(self) -> None: ...
    def add_task(self, text: str, user_id: Optional[int] = None, due_at: Optional[int] = None) -> int: ...
    def list_tasks(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Any]: ...
    def add_note(self, text: str, user_id: Optional[int] = None) -> int: ...
    def list_notes(
        self,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Any]: ...


# ---- Singleton instance ----
_MEMORY_INSTANCE: Optional[MemoryBackend] = None


# ---- SQLite Adapter ----
class _SQLiteAdapter(MemoryBackend):
    """
    Адаптер поверх procedural memory_sqlite.py.
    Гарантирует единый интерфейс MemoryBackend.
    """

    def __init__(self) -> None:
        sql.init_db()
        logger.info("SQLiteAdapter: DB initialized (path=%s)", getattr(sql, "_DB_PATH", "unknown"))

    def init(self) -> None:
        # БД инициализирована в __init__
        return

    def add_task(self, text: str, user_id: Optional[int] = None, due_at: Optional[int] = None) -> int:
        return sql.add_task(text=text, user_id=user_id, due_at=due_at)

    def list_tasks(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Any]:
        return sql.list_tasks(user_id=user_id, status=status, limit=limit, offset=offset)

    def add_note(self, text: str, user_id: Optional[int] = None) -> int:
        return sql.add_note(text=text, user_id=user_id)

    def list_notes(
        self,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Any]:
        return sql.list_notes(user_id=user_id, limit=limit, offset=offset)


# ---- Factory ----
def get_memory(backend: Optional[str] = None) -> MemoryBackend:
    """
    Возвращает singleton-инстанс MemoryBackend.
    backend: 'sqlite' | 'inmemory'.
    Если не указан, читается из окружения MEMORY_BACKEND (по умолчанию sqlite).
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
# Инициализируем singleton при загрузке модуля
get_memory()
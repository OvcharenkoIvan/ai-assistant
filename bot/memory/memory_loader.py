# bot/memory/memory_loader.py
from __future__ import annotations
import os
import logging
import asyncio
from typing import Optional, Dict, Any, List

from bot.core.config import DB_PATH
from .memory_sqlite import MemorySQLite
from .memory_base import MemoryBackend
from . import memory_inmemory as inm
from bot.integrations.calendar_sync import CalendarSync  # 👈 добавлено

logger = logging.getLogger(__name__)

# Singleton instance
_MEMORY_INSTANCE: Optional[MemoryBackend] = None


class _SQLiteAdapter(MemoryBackend):
    """
    Адаптер MemoryBackend поверх MemorySQLite.
    Сохраняет один экземпляр MemorySQLite для всего бота (путь к БД берём из config.DB_PATH).
    Поддерживает raw_text и extra, чтобы capture.py работал корректно.
    Также проксирует методы, необходимые интеграции с Google Calendar (oauth + sync helpers).
    """

    def __init__(self) -> None:
        # Единая БД для бота и setup-скрипта
        self._sqlite = MemorySQLite(DB_PATH)
        self._calendar_sync = CalendarSync(self._sqlite)  # 👈 инициализация календарного синка
        logger.info("SQLiteAdapter initialized (DB path: %s)", self._sqlite.db_path)

    def init(self) -> None:
        # DB уже инициализирована в __init__
        return

    # --------- Tasks (базовый интерфейс) ---------

    def add_task(
        self,
        text: str,
        user_id: Optional[int] = None,
        *,
        raw_text: Optional[str] = None,
        due_at: Optional[int] = None,
        extra: Optional[dict] = None
    ) -> int:
        task_id = self._sqlite.add_task(
            user_id=user_id or 0,
            text=text,
            raw_text=raw_text,
            due_at=due_at,
            extra=extra,
        )

        # --- PUSH → Google ---
        try:
            task = self._sqlite.get_task(task_id)
            asyncio.create_task(self._calendar_sync.on_task_created(user_id or 0, task))
        except Exception as e:
            logger.warning(f"[MemoryLoader] Failed to push new task to calendar: {e}")

        return task_id

    def update_task(self, task_id: int, **fields) -> bool:
        ok = self._sqlite.update_task(task_id, **fields)
        if ok:
            try:
                task = self._sqlite.get_task(task_id)
                user_id = getattr(task, "user_id", 0)
                asyncio.create_task(self._calendar_sync.on_task_updated(user_id, task))
            except Exception as e:
                logger.warning(f"[MemoryLoader] Failed to push task update: {e}")
        return ok

    def delete_task(self, task_id: int) -> bool:
        task = self._sqlite.get_task(task_id)
        ok = self._sqlite.delete_task(task_id)
        if ok and task:
            try:
                user_id = getattr(task, "user_id", 0)
                asyncio.create_task(self._calendar_sync.on_task_deleted(user_id, task))
            except Exception as e:
                logger.warning(f"[MemoryLoader] Failed to push task deletion: {e}")
        return ok

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

    # --------- Notes ---------

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

    # --------- OAuth tokens (прокси для интеграций) ---------

    def upsert_oauth_token(self, user_id: str, provider: str, token_json: Dict[str, Any],
                           *, expiry: Optional[int] = None, scopes: Optional[List[str]] = None) -> None:
        self._sqlite.upsert_oauth_token(user_id, provider, token_json, expiry=expiry, scopes=scopes)

    def get_oauth_token(self, user_id: str, provider: str):
        return self._sqlite.get_oauth_token(user_id, provider)

    def delete_oauth_token(self, user_id: str, provider: str) -> bool:
        return self._sqlite.delete_oauth_token(user_id, provider)

    # --------- Calendar sync helpers (прокси) ---------

    def set_task_calendar_link(self, task_id: int, *, calendar_id: Optional[str],
                               event_id: Optional[str], event_etag: Optional[str] = None,
                               google_updated_at: Optional[int] = None) -> bool:
        return self._sqlite.set_task_calendar_link(
            task_id,
            calendar_id=calendar_id,
            event_id=event_id,
            event_etag=event_etag,
            google_updated_at=google_updated_at,
        )

    def clear_task_calendar_link(self, task_id: int) -> bool:
        return self._sqlite.clear_task_calendar_link(task_id)

    def get_task_by_calendar_event(self, user_id: int, calendar_id: str, event_id: str):
        return self._sqlite.get_task_by_calendar_event(user_id, calendar_id, event_id)

    def list_tasks_missing_calendar_link(self, user_id: int):
        return self._sqlite.list_tasks_missing_calendar_link(user_id)

    def list_tasks_modified_since(self, ts_epoch: int, user_id: Optional[int] = None):
        return self._sqlite.list_tasks_modified_since(ts_epoch, user_id)

    def mark_task_locally_modified(self, task_id: int) -> bool:
        return self._sqlite.mark_task_locally_modified(task_id)


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
# bot/scheduler/jobs.py
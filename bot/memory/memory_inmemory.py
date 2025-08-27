# bot/memory/memory_inmemory.py
from __future__ import annotations
import time
import logging
import itertools
from typing import List, Dict, Any, Optional

from .memory_base import MemoryBackend

logger = logging.getLogger(__name__)


class InMemoryMemory(MemoryBackend):
    """
    In-memory реализация хранилища.
    Полностью совместима с MemoryBackend.
    Используется для локальной разработки и юнит-тестов.

    ⚠️ Все данные хранятся в оперативной памяти и теряются при перезапуске процесса.
    """

    def __init__(self) -> None:
        # отдельные последовательности id для задач и заметок
        self._task_id_counter = itertools.count(1)
        self._note_id_counter = itertools.count(1)

        # внутренние "таблицы"
        self._tasks: List[Dict[str, Any]] = []
        self._notes: List[Dict[str, Any]] = []

    def init(self) -> None:
        """Сбрасывает все данные (чистый старт)."""
        logger.info("InMemoryMemory: init (очистка данных)")
        self._task_id_counter = itertools.count(1)
        self._note_id_counter = itertools.count(1)
        self._tasks.clear()
        self._notes.clear()

    def add_task(
        self,
        text: str,
        user_id: Optional[int] = None,
        due_at: Optional[int] = None
    ) -> int:
        task_id = next(self._task_id_counter)
        row = {
            "id": task_id,
            "user_id": user_id,
            "text": text,
            "due_at": due_at,
            "status": "open",
            "created_at": int(time.time())
        }
        self._tasks.append(row)
        logger.debug("InMemoryMemory: add_task id=%s", task_id)
        return task_id

    def add_note(
        self,
        text: str,
        user_id: Optional[int] = None
    ) -> int:
        note_id = next(self._note_id_counter)
        row = {
            "id": note_id,
            "user_id": user_id,
            "text": text,
            "created_at": int(time.time())
        }
        self._notes.append(row)
        logger.debug("InMemoryMemory: add_note id=%s", note_id)
        return note_id

    def list_tasks(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        rows = self._tasks
        if user_id is not None:
            rows = [r for r in rows if r.get("user_id") == user_id]
        if status is not None:
            rows = [r for r in rows if r.get("status") == status]
        rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)
        return rows[offset: offset + limit] if limit is not None else rows[offset:]

    def list_notes(
        self,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        rows = self._notes
        if user_id is not None:
            rows = [r for r in rows if r.get("user_id") == user_id]
        rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)
        return rows[offset: offset + limit] if limit is not None else rows[offset:]

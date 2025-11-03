# bot/memory/memory_base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class MemoryBackend(ABC):
    """
    Синхронный интерфейс для бекенда памяти.
    Реальные реализации могут принимать расширенные поля (raw_text, extra, etc.).
    """

    @abstractmethod
    def init(self) -> None:
        """Инициализация (создание таблиц/структур)."""

    @abstractmethod
    def add_task(
        self,
        text: str,
        user_id: Optional[int] = None,
        *,
        due_at: Optional[int] = None,
        **kwargs: Any
    ) -> int:
        """Добавить задачу. Вернуть id."""

    @abstractmethod
    def add_note(
        self,
        text: str,
        user_id: Optional[int] = None,
        **kwargs: Any
    ) -> int:
        """Добавить заметку. Вернуть id."""

    @abstractmethod
    def list_tasks(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Any]:
        """Список задач (объекты или словари — зависит от реализации)."""

    @abstractmethod
    def list_notes(
        self,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> List[Any]:
        """Список заметок."""
    
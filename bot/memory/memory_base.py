# bot/memory/memory_base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class MemoryBackend(ABC):
    """
    Синхронный интерфейс для бекенда памяти.
    Поддерживает минимальный набор операций, используемый ботом.
    """

    @abstractmethod
    def init(self) -> None:
        """Инициализация бекенда (создание таблиц/структур)."""

    @abstractmethod
    def add_task(self, text: str, user_id: Optional[int] = None, due_at: Optional[int] = None) -> int:
        """Добавить задачу. Вернуть id задачи."""

    @abstractmethod
    def add_note(self, text: str, user_id: Optional[int] = None) -> int:
        """Добавить заметку. Вернуть id заметки."""

    @abstractmethod
    def list_tasks(self, user_id: Optional[int] = None, status: Optional[str] = None,
                   limit: Optional[int] = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Список задач в виде списка словарей."""

    @abstractmethod
    def list_notes(self, user_id: Optional[int] = None, limit: Optional[int] = 100,
                   offset: int = 0) -> List[Dict[str, Any]]:
        """Список заметок в виде списка словарей."""

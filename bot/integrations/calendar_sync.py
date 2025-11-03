# bot/integrations/calendar_sync.py
from __future__ import annotations

import logging
import asyncio
from bot.integrations.google_calendar import GoogleCalendarClient

logger = logging.getLogger(__name__)


class CalendarSync:
    """
    Менеджер двусторонней синхронизации.
    Работает через уже инициализированный MemoryBackend (_mem).
    """

    def __init__(self, mem_backend):
        self.mem = mem_backend
        self.gc = GoogleCalendarClient(mem_backend)

    async def on_task_created(self, user_id: int, task):
        """Отправляем новую задачу в Google Calendar"""
        try:
            if not self.gc.is_connected(user_id):
                return
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.gc.create_event(user_id, task)
            )
            logger.info(f"[CalendarSync] ✅ Created event for task {task.id}")
        except Exception as e:
            logger.warning(f"[CalendarSync] Failed to create event: {e}")

    async def on_task_updated(self, user_id: int, task):
        """При изменении задачи синхронизируем с Google"""
        try:
            if not self.gc.is_connected(user_id):
                return
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.gc.update_event(user_id, task)
            )
            logger.info(f"[CalendarSync] 🔁 Updated event for task {task.id}")
        except Exception as e:
            logger.warning(f"[CalendarSync] Failed to update event: {e}")

    async def on_task_deleted(self, user_id: int, task):
        """Удаляем из Google Calendar"""
        try:
            if not self.gc.is_connected(user_id):
                return
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.gc.delete_event(user_id, task)
            )
            logger.info(f"[CalendarSync] ❌ Deleted event for task {task.id}")
        except Exception as e:
            logger.warning(f"[CalendarSync] Failed to delete event: {e}")

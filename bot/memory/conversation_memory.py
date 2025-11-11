# bot/memory/conversation_memory.py
"""
Conversational memory manager for AI Assistant.

Функции:
- сохраняет и извлекает последние сообщения пользователя/ассистента;
- делает сводку (summary) длинных диалогов при превышении лимита;
- готовит контекст для GPT (history + summary).
"""

import time
from typing import List, Dict, Optional, Any
from openai import OpenAI
from bot.memory.memory_sqlite import MemorySQLite, ConversationMessage

# параметры
MAX_HISTORY_MESSAGES = 50
SUMMARY_TRIGGER = 40  # при 40+ сообщений делаем summary


class ConversationMemoryManager:
    def __init__(self, db: MemorySQLite, openai_client: OpenAI):
        self.db = db
        self.client = openai_client

    # -------------------
    # Message management
    # -------------------

    def add_message(self, user_id: int, role: str, content: str, meta: Optional[Dict[str, Any]] = None):
        """Сохраняет новое сообщение."""
        self.db.add_conversation_message(user_id, role, content, meta_json=meta)
        # если история слишком длинная — сворачиваем
        count = len(self.db.list_conversation_messages(user_id, limit=MAX_HISTORY_MESSAGES + 1))
        if count > SUMMARY_TRIGGER:
            self._update_summary(user_id)
            self.db.prune_conversation_history(user_id, keep_last=MAX_HISTORY_MESSAGES)

    def get_recent_messages(self, user_id: int, limit: int = 10) -> List[ConversationMessage]:
        return self.db.list_conversation_messages(user_id, limit=limit, order="asc")

    # -------------------
    # Summary logic
    # -------------------

    def _update_summary(self, user_id: int):
        """Создаёт или обновляет краткую сводку истории через GPT."""
        messages = self.db.list_conversation_messages(user_id, limit=SUMMARY_TRIGGER, order="asc")
        if not messages:
            return

        # Соберём контекст для суммаризации
        text_blocks = [f"{m.role}: {m.content}" for m in messages[-SUMMARY_TRIGGER:]]
        joined = "\n".join(text_blocks)

        system_prompt = (
            "Ты — AI-ассистент. Сожми историю общения в краткую сводку, "
            "сохранив суть целей, контекста и привычек пользователя."
        )

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": joined},
            ],
            max_tokens=300,
        )

        summary = response.choices[0].message.content.strip()
        self.db.set_conversation_summary(user_id, summary)

    # -------------------
    # Context for GPT
    # -------------------

    def build_prompt_context(self, user_id: int) -> List[Dict[str, str]]:
        """
        Возвращает список сообщений (для передачи в GPT),
        комбинируя summary + последние сообщения.
        """
        out: List[Dict[str, str]] = []
        summary = self.db.get_conversation_summary(user_id)
        if summary:
            out.append({
                "role": "system",
                "content": f"Сводка предыдущего контекста: {summary.summary_text}",
            })
        recent = self.db.list_conversation_messages(user_id, limit=10, order="asc")
        for m in recent:
            out.append({"role": m.role, "content": m.content})
        return out

    # -------------------
    # Maintenance
    # -------------------

    def reset(self, user_id: int):
        """Очистка всей истории и summary."""
        self.db.delete_conversation_history(user_id)
    
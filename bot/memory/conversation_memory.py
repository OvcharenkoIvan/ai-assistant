# bot/memory/conversation_memory.py
"""
Conversational memory manager for AI Assistant.

Функции:
- сохраняет и извлекает сообщения пользователя/ассистента;
- при превышении лимита даёт сигнал, что пора сделать summary;
- по запросу делает краткую summary через GPT (через переданную функцию);
- готовит контекст для GPT (summary + последние сообщения).
"""

from __future__ import annotations

from typing import List, Dict, Optional, Any

from bot.memory.memory_sqlite import MemorySQLite, ConversationMessage

# Сколько сообщений максимум держим "как есть"
MAX_HISTORY_MESSAGES = 50
# После какого числа сообщений начинаем предлагать сделать summary
SUMMARY_TRIGGER = 40  # при 40+ сообщений имеет смысл сжать историю


class ConversationMemoryManager:
    def __init__(self, db: MemorySQLite):
        """
        db — адаптер хранения (MemorySQLite).
        Никаких прямых зависимостей от OpenAI здесь нет.
        """
        self.db = db

    # -------------------
    # Message management
    # -------------------

    def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Сохраняет новое сообщение в conversation_memory.
        Возвращает id вставленной записи.
        """
        return self.db.add_conversation_message(
            user_id=user_id,
            role=role,
            content=content,
            meta_json=meta,
        )

    def get_recent_messages(self, user_id: int, limit: int = 10) -> List[ConversationMessage]:
        """
        Возвращает последние limit сообщений по ts_epoch (по возрастанию).
        """
        # Внутри list_conversation_messages можно запросить в обратном порядке и развернуть,
        # но у нас уже есть order="asc".
        return self.db.list_conversation_messages(
            user_id=user_id,
            limit=limit,
            order="asc",
        )

    # -------------------
    # Summary logic
    # -------------------

    def should_update_summary(self, user_id: int) -> bool:
        """
        Эвристика: если у пользователя уже >= SUMMARY_TRIGGER сообщений —
        можно запускать построение summary.
        """
        msgs = self.db.list_conversation_messages(
            user_id=user_id,
            limit=SUMMARY_TRIGGER + 1,
            order="desc",
        )
        return len(msgs) >= SUMMARY_TRIGGER

    def update_summary_via_gpt(
        self,
        user_id: int,
        ask_sync_fn,
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> None:
        """
        Строит / обновляет summary истории пользователя через sync-функцию GPT.

        ask_sync_fn: callable(messages: List[dict], model, temperature, max_tokens) -> str
        (мы будем передавать сюда _ask_gpt_sync из bot.gpt.client)

        ВНИМАНИЕ: метод синхронный. Запускать его из async-кода нужно через
        asyncio.to_thread(...), чтобы не блокировать event loop.
        """
        # Берём последние MAX_HISTORY_MESSAGES сообщений (от новых к старым)
        msgs: List[ConversationMessage] = self.db.list_conversation_messages(
            user_id=user_id,
            limit=MAX_HISTORY_MESSAGES,
            order="desc",
        )
        if not msgs:
            return

        # Разворачиваем в хронологический порядок (старые → новые)
        msgs = list(reversed(msgs))

        text_blocks: List[str] = [
            f"{m.role}: {m.content}"
            for m in msgs
        ]
        joined = "\n".join(text_blocks)

        system_prompt = (
            "Ты — персональный AI-ассистент пользователя. "
            "Сожми историю общения в краткую, структурированную сводку: "
            "цели пользователя, контекст проектов, предпочтения, важные факты. "
            "Не пересказывай дословно, а выделяй суть."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": joined},
        ]

        try:
            summary = ask_sync_fn(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            # Здесь специально не логируем — логика логирования снаружи
            return

        if not summary:
            return

        summary_text = summary.strip()
        if not summary_text:
            return

        # Сохраняем summary в отдельную таблицу
        self.db.set_conversation_summary(user_id, summary_text)
        # Подрезаем историю, оставляя последние MAX_HISTORY_MESSAGES сообщений
        self.db.prune_conversation_history(user_id, keep_last=MAX_HISTORY_MESSAGES)

    # -------------------
    # Context for GPT
    # -------------------

    def build_prompt_context(self, user_id: int) -> List[Dict[str, str]]:
        """
        Возвращает список сообщений (для передачи в GPT),
        комбинируя summary + последние сообщения.
        Формат: [{"role": "...", "content": "..."}, ...]
        """
        out: List[Dict[str, str]] = []

        # 1) Добавляем summary, если есть
        summary = self.db.get_conversation_summary(user_id)
        if summary:
            out.append(
                {
                    "role": "system",
                    "content": f"Сводка предыдущего контекста с пользователем:\n{summary.summary_text}",
                }
            )

        # 2) Добавляем последние сообщения (user/assistant/system)
        recent = self.db.list_conversation_messages(
            user_id=user_id,
            limit=10,
            order="asc",
        )
        for m in recent:
            out.append(
                {
                    "role": m.role,
                    "content": m.content,
                }
            )

        return out

    # -------------------
    # Maintenance
    # -------------------

    def reset(self, user_id: int) -> None:
        """Полная очистка истории и summary пользователя."""
        self.db.delete_conversation_history(user_id)

# bot/tests/test_capture_formatters.py (Вызов теста: python -m bot.tests.test_capture_formatters)
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from bot.memory.capture import offer_capture, handle_capture_callback, capture_store, TASK
from bot.memory.formatters import format_text, parse_due_at
from telegram import Update

@pytest.mark.asyncio
async def test_format_text_with_mocked_gpt():
    """Тестируем format_text для всех типов и fallback."""

    raw_text = "Написать письмо до завтра"

    # Мокаем ask_gpt
    async def mock_ask_gpt(prompt: str):
        if "email" in prompt:
            return '{"subject": "Тема", "body": "Содержание письма", "to": ["a@b.com"], "due_at": "завтра"}'
        elif "meeting" in prompt:
            return '{"tasks":[{"task":"Сделать отчёт","due_at":"послезавтра"}],"notes":["Обсудить проект"]}'
        else:  # vector
            return "нормализованный текст"

    # Мокаем load_prompt (чтобы не лазил в файлы)
    def mock_load_prompt(fmt_type: str):
        return f"PROMPT({fmt_type})"

    with patch("bot.memory.formatters.ask_gpt", new=mock_ask_gpt), \
         patch("bot.memory.formatters.load_prompt", new=mock_load_prompt):

        # email
        result_email = await format_text(raw_text, fmt_type="email")
        assert result_email["subject"] == "Тема"
        assert result_email["body"] == "Содержание письма"
        assert isinstance(result_email["due_at"], int)

        # meeting
        result_meeting = await format_text(raw_text, fmt_type="meeting")
        assert len(result_meeting["tasks"]) == 1
        assert isinstance(result_meeting["tasks"][0]["due_at"], int)
        assert "Обсудить проект" in result_meeting["notes"]

        # vector
        result_vector = await format_text(raw_text, fmt_type="vector")
        assert "vector_text" in result_vector

    # Проверяем fallback на невалидный JSON
    async def mock_bad_gpt(prompt: str):
        return "невалидный JSON"

    with patch("bot.memory.formatters.ask_gpt", new=mock_bad_gpt), \
         patch("bot.memory.formatters.load_prompt", new=mock_load_prompt):

        fallback_result = await format_text(raw_text, fmt_type="email")
        assert fallback_result["body"] == raw_text
        assert fallback_result["subject"] is None


@pytest.mark.asyncio
async def test_capture_integration_with_formatters():
    """Тестируем интеграцию capture -> formatters -> сохранение."""

    class DummyMessage:
        text = "Сделать отчёт"
        async def reply_text(self, text, **kwargs):
            self.reply_text_called = text
            return self

    class DummyUser:
        id = 123

    class DummyCallback:
        data = ""
        message = DummyMessage()
        from_user = DummyUser()
        async def answer(self, **kwargs):
            self.answer_called = True
        async def edit_text(self, text):
            self.edited_text = text

    message = DummyMessage()
    update_offer = Update(update_id=1, message=message)
    context = AsyncMock()

    # Запускаем offer_capture
    await offer_capture(update_offer, context)
    assert len(capture_store) == 1
    capture_id = list(capture_store.keys())[0]
    assert capture_store[capture_id] == message.text

    # Мокаем ask_gpt + load_prompt
    async def mock_ask_gpt(prompt: str):
        return '{"body":"Сделать отчёт","raw_text":"Сделать отчёт"}'
    def mock_load_prompt(fmt_type: str):
        return f"PROMPT({fmt_type})"

    with patch("bot.memory.formatters.ask_gpt", new=mock_ask_gpt), \
         patch("bot.memory.formatters.load_prompt", new=mock_load_prompt):

        callback = DummyCallback()
        callback.data = f"capture:{TASK}:{capture_id}"
        update_callback = Update(update_id=2, callback_query=callback)
        await handle_capture_callback(update_callback, context)

        # Проверяем, что capture_store очистился
        assert capture_id not in capture_store
        assert hasattr(callback, "answer_called")
        assert hasattr(callback, "edited_text")
        assert "✅ Задача сохранена" in callback.edited_text


@pytest.mark.asyncio
async def test_parse_due_at():
    """Тестируем parse_due_at для разных выражений."""
    texts = [
        "сегодня", "завтра", "послезавтра",
        "следующий понедельник", "следующая пятница",
        "через 2 дня", "next Monday", "tomorrow 15:00"
    ]
    for t in texts:
        ts = parse_due_at(t)
        assert ts is None or isinstance(ts, int)
        if ts:
            assert ts > int(datetime.now().timestamp()) - 10


# Запуск напрямую: python -m bot.tests.test_capture_formatters
if __name__ == "__main__":
    print("\n🚀 Запуск тестов capture_formatters")
    asyncio.run(test_format_text_with_mocked_gpt())
    asyncio.run(test_capture_integration_with_formatters())
    asyncio.run(test_parse_due_at())
    print("✅ Все тесты успешно выполнены")

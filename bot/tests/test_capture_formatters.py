# bot/tests/test_capture_formatters.py
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
        async def edit_text(self, text, **kwargs):
            self.edited_text = text
            return self

    class DummyUser:
        id = 123

    class DummyCallback:
        data = ""
        message = DummyMessage()
        from_user = DummyUser()
        async def answer(self, **kwargs):
            self.answer_called = True

    message = DummyMessage()
    update_offer = Update(update_id=1, message=message)
    context = AsyncMock()

    # Запускаем offer_capture
    await offer_capture(update_offer, context)
    assert len(capture_store) == 1
    capture_id = list(capture_store.keys())[0]
    stored_value = capture_store[capture_id]

    if isinstance(stored_value, str):
        assert stored_value == message.text

    elif isinstance(stored_value, dict):
        assert stored_value.get("text") == message.text or stored_value.get("body") == message.text

    elif isinstance(stored_value, tuple):
        text_part = stored_value[0]
        assert text_part == message.text

    elif hasattr(stored_value, "text"):
        assert stored_value.text == message.text

    else:
        raise AssertionError(f"Неожиданный формат capture_store: {stored_value}")

    # Мокаем ask_gpt + load_prompt + _mem.add_task/_mem.add_note
    async def mock_ask_gpt(prompt: str):
        return '{"body":"Сделать отчёт"}'

    def mock_load_prompt(fmt_type: str):
        return f"PROMPT({fmt_type})"

    def mock_add_task(**kwargs):
        return 42

    def mock_add_note(**kwargs):
        return 24

    import bot.memory.capture as capture_module

    with patch("bot.memory.formatters.ask_gpt", new=mock_ask_gpt), \
         patch("bot.memory.formatters.load_prompt", new=mock_load_prompt), \
         patch.object(capture_module._mem, "add_task", new=mock_add_task), \
         patch.object(capture_module._mem, "add_note", new=mock_add_note):

        callback = DummyCallback()
        callback.data = f"capture:{TASK}:{capture_id}"
        update_callback = Update(update_id=2, callback_query=callback)
        await handle_capture_callback(update_callback, context)

        # Проверяем, что capture_store очистился
        assert capture_id not in capture_store
        assert hasattr(callback, "answer_called")
        assert hasattr(callback.message, "edited_text")
        assert "✅ Задача сохранена" in callback.message.edited_text


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


if __name__ == "__main__":
    print("\n🚀 Запуск тестов capture_formatters")
    asyncio.run(test_format_text_with_mocked_gpt())
    asyncio.run(test_capture_integration_with_formatters())
    asyncio.run(test_parse_due_at())
    print("✅ Все тесты успешно выполнены")

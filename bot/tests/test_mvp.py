# bot/tests/test_mvp.py
import sys
from pathlib import Path
import asyncio
import logging
from types import SimpleNamespace

# --- Добавляем корень проекта в sys.path ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

# --- Импорты наших модулей ---
from bot.memory.memory_sqlite import init_db, add_task, add_note, list_tasks, list_notes
from bot.memory.intent import classify_intent, process_intent
from bot.memory.capture import offer_capture, handle_capture_callback

logging.basicConfig(level=logging.INFO)

# --- Заглушка для ask_gpt ---
# В тестах GPT нам не нужен, поэтому возвращаем сразу "task" или "note"
import bot.memory.intent as intent_module
async def fake_ask_gpt(prompt: str, system: str = None) -> str:
    # Для теста можно вернуть "task" или "note" в зависимости от текста
    if "задача" in prompt.lower() or "сделать" in prompt.lower():
        return "task"
    elif "заметка" in prompt.lower() or "идея" in prompt.lower():
        return "note"
    return "none"

intent_module.ask_gpt = fake_ask_gpt  # <- подключаем заглушку

# --- Fake объекты для теста ---
class FakeMessage:
    def __init__(self, text, user_id=123):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
    async def answer(self, text, reply_markup=None):
        print(f"[Bot Answer] {text}")
    async def edit_text(self, text):
        print(f"[Edit Message] {text}")

class FakeCallback:
    def __init__(self, data, user_id=123):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage("Original message")
    async def answer(self, text: str = None, show_alert: bool = False):
        print(f"[Callback answer] text={text} show_alert={show_alert}")

# --- Главная функция теста ---
async def run_tests():
    print("=== Тестирование SQLite-хранилища MVP ===")
    init_db()
    print("База инициализирована ✅\n")

    # --- Тест Intent ---
    test_texts = [
        "Сделать завтра отчёт",
        "Записать идею для проекта",
        "Привет, как дела?"
    ]

    for text in test_texts:
        intent = await classify_intent(text)  # <- обязательно await для async функции
        print(f"Text: '{text}' -> Intent: {intent}")

        # Если задача или заметка, вызываем offer_capture
        msg = FakeMessage(text)
        if intent in ("task", "note"):
            await offer_capture(msg)

    # --- Тест сохранения через callback ---
    print("\n=== Тест callback сохранения ===")
    task_cb = FakeCallback("capture:task:Сделать отчёт")
    note_cb = FakeCallback("capture:note:Идея для заметки")
    await handle_capture_callback(task_cb)
    await handle_capture_callback(note_cb)

    # --- Проверяем данные в БД ---
    tasks = list_tasks()
    notes = list_notes()
    print("\nTasks in DB:", tasks)
    print("Notes in DB:", notes)

# --- Запуск теста ---
if __name__ == "__main__":
    asyncio.run(run_tests())

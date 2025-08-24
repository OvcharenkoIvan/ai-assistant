"""
Интеграционный тест MVP:
- SQLite-хранилище
- Intent классификация
- Smart Capture (inline-кнопки)

Запуск:
$ python bot/tests/test_mvp.py
"""

import sys
from pathlib import Path
import asyncio
import logging
from types import SimpleNamespace
import os

# --- Добавляем корень проекта ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Импорты проекта ---
from bot.memory.memory_sqlite import init_db, add_task, add_note, get_tasks, get_notes
from bot.memory.intent import classify_intent, process_intent
from bot.memory.capture import offer_capture, handle_capture_callback

# --- Очистка базы перед тестом ---
DB_PATH = ROOT_DIR / "memory.db"
if DB_PATH.exists():
    DB_PATH.unlink()
    logging.info("Старая база удалена ✅")

# --- Фейковые объекты для теста ---
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
    async def answer(self, show_alert=False):
        print(f"[Callback answer] show_alert={show_alert}")

# --- Основной тест ---
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
        intent = classify_intent(text)
        print(f"Text: '{text}' -> Intent: {intent}")

        msg = FakeMessage(text)
        if intent in ("task", "note"):
            await offer_capture(msg)

    # --- Тест callback сохранения ---
    print("\n=== Тест callback сохранения ===")
    task_cb = FakeCallback("capture:task:Сделать отчёт")
    note_cb = FakeCallback("capture:note:Идея для заметки")
    await handle_capture_callback(task_cb)
    await handle_capture_callback(note_cb)

    # --- Проверка данных в базе ---
    tasks = get_tasks()
    notes = get_notes()
    print("\n--- Данные в БД ---")
    print(f"Tasks: {tasks}")
    print(f"Notes: {notes}")

if __name__ == "__main__":
    asyncio.run(run_tests())

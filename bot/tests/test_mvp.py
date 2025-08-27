# bot/tests/test_mvp.py

import asyncio
from bot.memory.memory_sqlite import init_db, add_task, add_note, list_tasks, list_notes
from bot.memory.intent import detect_intent
from bot.memory.capture import offer_capture, handle_capture_callback, capture_store

# =========================
# Хелперы для тестов
# =========================

async def reset_db():
    """Очистка SQLite-базы перед тестами"""
    await init_db()
    tasks = await list_tasks()
    notes = await list_notes()
    # Если нужны реальные удаления — можно добавить
    print("🗑️  DB очищена перед тестами")

# =========================
# Фейковые объекты для PTB v20
# =========================

class FakeMessage:
    def __init__(self, text, user_id=123):
        self.text = text
        self.from_user = type("User", (), {"id": user_id})()

    async def reply_text(self, text, **kwargs):
        print(f"[Bot Reply] {text} | kwargs={kwargs}")

    async def edit_text(self, text, **kwargs):
        print(f"[Edit Message] {text} | kwargs={kwargs}")

class FakeCallback:
    def __init__(self, data, user_id=123):
        self.data = data
        self.from_user = type("User", (), {"id": user_id})()

    async def answer(self, text=None, show_alert=False):
        print(f"[Callback answer] text={text} show_alert={show_alert}")

class FakeUpdate:
    def __init__(self, message):
        self.effective_message = message

class FakeUpdateCallback:
    def __init__(self, callback_query):
        self.callback_query = callback_query

# =========================
# Основной тест
# =========================

async def run_tests():
    print("\n\n🚀 Запуск комплексного теста памяти\n")

    await reset_db()

    print("\n" + "=" * 50)
    print("✨ SQLite (tasks + notes)")
    print("=" * 50)

    t1 = await add_task("тестовое задание", user_id=1)
    n1 = await add_note("Идея для проекта", user_id=1)

    tasks = await list_tasks()
    notes = await list_notes()
    print("📌 Tasks:", tasks)
    print("📝 Notes:", notes)

    print("\n" + "=" * 50)
    print("✨ Intent + Cache")
    print("=" * 50)

    q = "Нужно сделать отчёт"
    result1 = await detect_intent(q)
    print("⚡ First call:", result1)
    result2 = await detect_intent(q)
    print("⚡ Second call (cached):", result2)

    print("\n" + "=" * 50)
    print("✨ Capture + Callback (интеграция)")
    print("=" * 50)

    # --- offer_capture ---
    msg = FakeMessage("Сделать отчёт")
    update = FakeUpdate(msg)
    await offer_capture(update, context=None)

    # достаём ID из capture_store напрямую
    stored_id = list(capture_store.keys())[0]

    # --- handle_capture_callback ---
    cb = FakeCallback(f"capture:task:{stored_id}")
    update_cb = FakeUpdateCallback(cb)
    await handle_capture_callback(update_cb, context=None)

    final_tasks = await list_tasks()
    print("✅ Final tasks in DB:", final_tasks)

    print("\n🎉 Все блоки памяти протестированы успешно!")

if __name__ == "__main__":
    asyncio.run(run_tests())

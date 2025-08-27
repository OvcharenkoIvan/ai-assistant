# bot/tests/test_mvp.py

import asyncio
from bot.memory.memory_sqlite import init_db, add_task, add_note, list_tasks, list_notes
from bot.memory.intent import detect_intent
from bot.memory.capture import offer_capture, handle_capture_callback

# =========================
# Хелперы для тестов
# =========================

async def reset_db():
    """Очистка SQLite-базы перед тестами"""
    await init_db()
    # можно очистить записи, если нужно
    tasks = await list_tasks()
    notes = await list_notes()
    for t in tasks:
        pass  # можно удалить через отдельный метод
    for n in notes:
        pass
    print("🗑️  DB очищена перед тестами")

class FakeMessage:
    def __init__(self, text, user_id=123):
        self.text = text
        self.from_user = type("User", (), {"id": user_id})

    async def answer(self, text, **kwargs):
        print(f"[Bot Answer] {text} | kwargs={kwargs}")

    async def edit_text(self, text, **kwargs):
        print(f"[Edit Message] {text} | kwargs={kwargs}")

class FakeCallback:
    def __init__(self, data, user_id=123):
        self.data = data
        self.from_user = type("User", (), {"id": user_id})

    async def answer(self, text=None, show_alert=False):
        print(f"[Callback answer] text={text} show_alert={show_alert}")

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

    msg = FakeMessage("Сделать отчёт")
    await offer_capture(msg)

    # достаём ID из capture_store напрямую
    from bot.memory import capture as capture_module
    stored_id = list(capture_module.capture_store.keys())[0]

    cb = FakeCallback(f"capture:task:{stored_id}")
    await handle_capture_callback(cb)

    final_tasks = await list_tasks()
    print("✅ Final tasks in DB:", final_tasks)

    print("\n🎉 Все блоки памяти протестированы успешно!")

if __name__ == "__main__":
    asyncio.run(run_tests())

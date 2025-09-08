# bot/tests/test_tasks_sqlite.py
import pytest
import sqlite3
import time
from pathlib import Path
from bot.memory.memory_sqlite import MemorySQLite

# Путь к тестовой базе
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assistant_test.db"

@pytest.fixture(scope="module")
def mem():
    """Создаём чистый экземпляр памяти для тестов."""
    # Создаём папку data, если её нет
    if not DB_PATH.parent.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Удаляем старую базу, если есть
    if DB_PATH.exists():
        DB_PATH.unlink()
    memory = MemorySQLite(db_path=DB_PATH)
    yield memory
    # Закрываем соединения и удаляем тестовую базу
    del memory
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except PermissionError:
            # В Windows иногда файл ещё используется, можно игнорировать
            pass

def test_tasks_add_and_migrate_due_at(mem: MemorySQLite):
    """Полная проверка задач: старые задачи без due_at, добавление новой задачи с due_at."""

    # --- 1. Добавляем старые задачи без due_at ---
    old_task_ids = []
    for i in range(3):
        task_id = mem.add_task(user_id=i + 1, text=f"Старая задача {i}", due_at=None)
        old_task_ids.append(task_id)

    # Проверяем, что поле due_at есть, но None
    tasks_before = mem.list_tasks()
    assert len(tasks_before) == 3
    for t in tasks_before:
        assert hasattr(t, "due_at")
        assert t.due_at is None

    # --- 2. Миграция: создаём tasks_new с due_at, если нет колонки ---
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("PRAGMA foreign_keys=OFF;")
        cur.execute("PRAGMA table_info(tasks);")
        columns = [row[1] for row in cur.fetchall()]
        if "due_at" not in columns:
            cur.execute("ALTER TABLE tasks ADD COLUMN due_at INTEGER;")
        con.commit()

    # Проверяем, что старая информация сохранилась
    tasks_after = mem.list_tasks()
    assert len(tasks_after) == 3
    for t in tasks_after:
        assert hasattr(t, "due_at")
        assert t.due_at is None

    # --- 3. Добавляем новую задачу с due_at ---
    due_ts = int(time.time()) + 3600
    task_id = mem.add_task(user_id=10, text="Новая задача после миграции", due_at=due_ts)
    tasks_final = mem.list_tasks(user_id=10)
    assert len(tasks_final) == 1
    task = tasks_final[0]
    assert task.due_at == due_ts

    # --- 4. Проверяем корректность всех полей ---
    for key in ["id", "user_id", "text", "status", "created_at", "updated_at", "due_at"]:
        assert hasattr(task, key)
    assert task.text == "Новая задача после миграции"
    assert task.status == "open"
    assert task.user_id == 10
    assert isinstance(task.created_at, int)
    assert task.due_at == due_ts

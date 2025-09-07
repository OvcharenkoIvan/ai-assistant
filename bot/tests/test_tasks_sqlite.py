# bot/tests/test_tasks_sqlite_full.py
import pytest
import sqlite3
import time
from pathlib import Path

from bot.memory import memory_sqlite as mem

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assistant.db"


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Создаём чистую базу для тестов."""
    mem.init_db(reset=True)
    yield
    if DB_PATH.exists():
        DB_PATH.unlink()


def test_tasks_add_and_migrate_due_at():
    """Полная проверка задач: старые задачи, миграция, новые задачи с due_at."""

    # 1. Добавляем старые задачи без due_at
    old_task_ids = []
    for i in range(3):
        task_id = mem.add_task(text=f"Старая задача {i}", user_id=i + 1)
        old_task_ids.append(task_id)

    # Проверяем, что поле due_at есть, но None
    tasks_before = mem.list_tasks()
    for t in tasks_before:
        assert "due_at" in t
        assert t["due_at"] is None

    # 2. Миграция: создаём tasks_new с due_at и копируем данные
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=OFF;")
    con.execute("""
        CREATE TABLE IF NOT EXISTS tasks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NULL,
            text TEXT NOT NULL,
            due_at INTEGER NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at INTEGER NOT NULL
        );
    """)
    con.execute(
        "INSERT INTO tasks_new (id, user_id, text, status, created_at) "
        "SELECT id, user_id, text, status, created_at FROM tasks;"
    )
    con.execute("DROP TABLE tasks;")
    con.execute("ALTER TABLE tasks_new RENAME TO tasks;")
    con.commit()
    con.close()

    # Проверяем, что старая информация сохранилась
    tasks_after = mem.list_tasks()
    assert len(tasks_after) >= 3
    for t in tasks_after:
        assert "due_at" in t
        assert t["due_at"] is None

    # 3. Добавляем новую задачу с due_at
    due_ts = int(time.time()) + 3600
    task_id = mem.add_task("Новая задача после миграции", user_id=10, due_at=due_ts)
    tasks_final = mem.list_tasks(user_id=10)
    assert len(tasks_final) == 1
    assert tasks_final[0]["due_at"] == due_ts

    # 4. Проверяем корректность всех полей
    task = tasks_final[0]
    for key in ["id", "user_id", "text", "status", "created_at", "due_at"]:
        assert key in task
    assert task["text"] == "Новая задача после миграции"
    assert task["status"] == "open"
    assert task["user_id"] == 10
    assert isinstance(task["created_at"], int)
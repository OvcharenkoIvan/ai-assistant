# bot/memory/memory_sqlite.py
"""
SQLite-хранилище для ассистента.
Содержит: init_db, add_task, add_note, list_tasks, list_notes, get_task, get_note,
update_task_status, delete_task, delete_note, get_tasks, get_notes.
"""

from __future__ import annotations

import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "assistant.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db() -> None:
    con = _connect()
    with con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NULL,
                text TEXT NOT NULL,
                due_at INTEGER NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at INTEGER NOT NULL
            );
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);")
        con.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
        """)
    con.close()
    logger.info("SQLite: init_db completed (%s)", _DB_PATH)


def add_task(text: str, user_id: Optional[int] = None, due_at: Optional[int] = None) -> int:
    ts = int(time.time())
    con = _connect()
    with con:
        cur = con.execute(
            "INSERT INTO tasks (user_id, text, due_at, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (user_id, text, due_at, ts),
        )
        task_id = cur.lastrowid
    con.close()
    logger.debug("add_task -> id=%s user_id=%s", task_id, user_id)
    return task_id


def add_note(text: str, user_id: Optional[int] = None) -> int:
    ts = int(time.time())
    con = _connect()
    with con:
        cur = con.execute(
            "INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
            (user_id, text, ts),
        )
        note_id = cur.lastrowid
    con.close()
    logger.debug("add_note -> id=%s user_id=%s", note_id, user_id)
    return note_id


def list_tasks(user_id: Optional[int] = None, status: Optional[str] = None,
               limit: Optional[int] = 100, offset: int = 0) -> List[Dict[str, Any]]:
    con = _connect()
    try:
        q = "SELECT id, user_id, text, due_at, status, created_at FROM tasks"
        conds = []
        params: List[Any] = []
        if user_id is not None:
            conds.append("user_id = ?")
            params.append(user_id)
        if status is not None:
            conds.append("status = ?")
            params.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY created_at DESC"
        if limit is not None:
            q += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cur = con.execute(q, tuple(params))
        return [dict(row) for row in cur.fetchall()]
    finally:
        con.close()


def list_notes(user_id: Optional[int] = None, limit: Optional[int] = 100, offset: int = 0) -> List[Dict[str, Any]]:
    con = _connect()
    try:
        q = "SELECT id, user_id, text, created_at FROM notes"
        conds = []
        params: List[Any] = []
        if user_id is not None:
            conds.append("user_id = ?")
            params.append(user_id)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY created_at DESC"
        if limit is not None:
            q += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cur = con.execute(q, tuple(params))
        return [dict(row) for row in cur.fetchall()]
    finally:
        con.close()


# --- Новые функции для тестов и простого получения всех записей ---
def get_tasks() -> List[Dict[str, Any]]:
    """Возвращает все задачи без фильтров."""
    return list_tasks(limit=None)


def get_notes() -> List[Dict[str, Any]]:
    """Возвращает все заметки без фильтров."""
    return list_notes(limit=None)


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        cur = con.execute(
            "SELECT id, user_id, text, due_at, status, created_at FROM tasks WHERE id = ?",
            (task_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def get_note(note_id: int) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        cur = con.execute(
            "SELECT id, user_id, text, created_at FROM notes WHERE id = ?",
            (note_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def update_task_status(task_id: int, status: str) -> bool:
    con = _connect()
    with con:
        cur = con.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        updated = cur.rowcount > 0
    con.close()
    logger.debug("update_task_status id=%s status=%s updated=%s", task_id, status, updated)
    return updated


def delete_task(task_id: int) -> bool:
    con = _connect()
    with con:
        cur = con.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        deleted = cur.rowcount > 0
    con.close()
    logger.debug("delete_task id=%s deleted=%s", task_id, deleted)
    return deleted


def delete_note(note_id: int) -> bool:
    con = _connect()
    with con:
        cur = con.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        deleted = cur.rowcount > 0
    con.close()
    logger.debug("delete_note id=%s deleted=%s", note_id, deleted)
    return deleted


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.DEBUG)

    init_db()
    print("DB initialized at:", _DB_PATH)
    t = add_task("Тестовая задача из memory_sqlite.py")
    n = add_note("Тестовая заметка из memory_sqlite.py")
    print("Added task id:", t)
    print("Added note id:", n)
    print("Tasks:", list_tasks())
    print("Notes:", list_notes())

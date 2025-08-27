# bot/memory/memory_sqlite.py
"""
Асинхронное SQLite-хранилище для ассистента.
Все операции через asyncio.to_thread, чтобы не блокировать event loop.
"""

from __future__ import annotations
import sqlite3
import time
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import asyncio

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parents[2] / "data" / "assistant.db"))
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

# ---------------------
# Синхронная логика
# ---------------------
def _init_db_sync() -> None:
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

def _add_task_sync(text: str, user_id: Optional[int], due_at: Optional[int]) -> int:
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

def _list_tasks_sync(user_id: Optional[int] = None, status: Optional[str] = None,
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

def _add_note_sync(text: str, user_id: Optional[int] = None) -> int:
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

def _list_notes_sync(user_id: Optional[int] = None, limit: Optional[int] = 100, offset: int = 0) -> List[Dict[str, Any]]:
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

# ---------------------
# Асинхронные обёртки
# ---------------------
async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)

async def add_task(text: str, user_id: Optional[int] = None, due_at: Optional[int] = None) -> int:
    return await asyncio.to_thread(_add_task_sync, text, user_id, due_at)

async def list_tasks(user_id: Optional[int] = None, status: Optional[str] = None,
                     limit: Optional[int] = 100, offset: int = 0) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_list_tasks_sync, user_id, status, limit, offset)

async def add_note(text: str, user_id: Optional[int] = None) -> int:
    return await asyncio.to_thread(_add_note_sync, text, user_id)

async def list_notes(user_id: Optional[int] = None, limit: Optional[int] = 100, offset: int = 0) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_list_notes_sync, user_id, limit, offset)

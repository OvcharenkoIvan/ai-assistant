# bot/memory/memory_sqlite.py
"""
Production-ready SQLite storage (содержит только логику работы с БД).
Не импортирует Telegram / capture / handlers — чтобы избежать circular imports.
"""

from __future__ import annotations

import sqlite3
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from contextlib import contextmanager

Epoch = int
SCHEMA_VERSION = 2


@dataclass
class Task:
    id: int
    user_id: int
    text: str
    raw_text: Optional[str]
    status: str
    due_at: Optional[Epoch]
    created_at: Epoch
    updated_at: Epoch
    source: Optional[str]
    source_agent: Optional[str]
    extra: Optional[Dict[str, Any]]


@dataclass
class Note:
    id: int
    user_id: int
    text: str
    raw_text: Optional[str]
    created_at: Epoch
    updated_at: Epoch
    source: Optional[str]
    source_agent: Optional[str]
    extra: Optional[Dict[str, Any]]


class MemorySQLite:
    """
    SQLite-backed storage for tasks and notes.
    Важное: не импортирует ничего, что может обратно импортировать этот модуль.
    """

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        self.db_path = str(db_path)
        # инициализация схемы
        self.init_db()

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA foreign_keys=ON;")
            con.execute("PRAGMA busy_timeout=3000;")
            yield con
        finally:
            con.close()

    def init_db(self) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );
            """)
            cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_version';")
            # if empty, insert initial value 0 if table exists but empty
            cur.execute("SELECT COUNT(*) FROM schema_version;")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO schema_version(version) VALUES (0);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    raw_text TEXT,
                    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','archived')),
                    due_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    source TEXT,
                    source_agent TEXT,
                    extra TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    raw_text TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    source TEXT,
                    source_agent TEXT,
                    extra TEXT
                );
            """)
            self._migrate(con)
            self._ensure_indexes(con)

    def _ensure_indexes(self, con: sqlite3.Connection) -> None:
        cur = con.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_at ON tasks(due_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_due ON tasks(user_id, due_at);")

    def _get_version(self, con: sqlite3.Connection) -> int:
        cur = con.cursor()
        cur.execute("SELECT version FROM schema_version LIMIT 1;")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def _set_version(self, con: sqlite3.Connection, v: int) -> None:
        con.execute("UPDATE schema_version SET version=?;", (v,))

    def _column_exists(self, con: sqlite3.Connection, table: str, column: str) -> bool:
        cur = con.cursor()
        cur.execute(f"PRAGMA table_info({table});")
        return any(row[1] == column for row in cur.fetchall())

    def _migrate(self, con: sqlite3.Connection) -> None:
        current = self._get_version(con)
        if not self._column_exists(con, "tasks", "due_at"):
            con.execute("ALTER TABLE tasks ADD COLUMN due_at INTEGER;")
            current = max(current, 1)
        if current < SCHEMA_VERSION:
            self._set_version(con, SCHEMA_VERSION)

    @staticmethod
    def _now_epoch() -> Epoch:
        return int(time.time())

    @staticmethod
    def _to_epoch(value: Optional[Union[int, float]]) -> Optional[Epoch]:
        if value is None:
            return None
        try:
            iv = int(value)
            return iv if iv >= 0 else None
        except Exception:
            return None

    @staticmethod
    def _loads_optional_json(s: Optional[str]) -> Optional[Dict[str, Any]]:
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None

    # ----- CRUD tasks -----
    def add_task(self, user_id: int, text: str, *, raw_text: Optional[str] = None,
                 due_at: Optional[Union[int, float]] = None, status: str = "open",
                 source: Optional[str] = None, source_agent: Optional[str] = None,
                 extra: Optional[Dict[str, Any]] = None) -> int:
        created = updated = self._now_epoch()
        due = self._to_epoch(due_at)
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO tasks (user_id, text, raw_text, status, due_at, created_at, updated_at, source, source_agent, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (user_id, text, raw_text, status, due, created, updated, source, source_agent, extra_json))
            return int(cur.lastrowid)

    def get_task(self, task_id: int) -> Optional[Task]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, user_id, text, raw_text, status, due_at, created_at, updated_at, source, source_agent, extra
                FROM tasks WHERE id=?;
            """, (task_id,))
            r = cur.fetchone()
            if not r:
                return None
            return Task(id=r[0], user_id=r[1], text=r[2], raw_text=r[3], status=r[4],
                        due_at=r[5], created_at=r[6], updated_at=r[7],
                        source=r[8], source_agent=r[9], extra=self._loads_optional_json(r[10]))

    def list_tasks(self, user_id: Optional[int] = None, *, status: Optional[str] = None,
                   order_by: str = "due_at_nulls_last", limit: Optional[int] = None, offset: int = 0) -> List[Task]:
        with self._connect() as con:
            cur = con.cursor()
            clauses = []
            params: List[Any] = []
            if user_id is not None:
                clauses.append("user_id=?"); params.append(user_id)
            if status is not None:
                clauses.append("status=?"); params.append(status)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            if order_by == "created_desc":
                order_sql = "ORDER BY created_at DESC"
            elif order_by == "updated_desc":
                order_sql = "ORDER BY updated_at DESC"
            else:
                order_sql = "ORDER BY (due_at IS NULL), due_at ASC, id ASC"
            lim = f" LIMIT {int(limit)}" if limit is not None else ""
            off = f" OFFSET {int(offset)}" if offset else ""
            cur.execute(f"""
                SELECT id, user_id, text, raw_text, status, due_at, created_at, updated_at, source, source_agent, extra
                FROM tasks {where} {order_sql} {lim}{off};
            """, params)
            rows = cur.fetchall()
            return [Task(id=r[0], user_id=r[1], text=r[2], raw_text=r[3], status=r[4],
                         due_at=r[5], created_at=r[6], updated_at=r[7],
                         source=r[8], source_agent=r[9], extra=self._loads_optional_json(r[10])) for r in rows]

    def update_task(self, task_id: int, *, text: Optional[str] = None, raw_text: Optional[str] = None,
                    status: Optional[str] = None, due_at: Optional[Union[int, float, None]] = None,
                    source: Optional[str] = None, source_agent: Optional[str] = None,
                    extra: Optional[Dict[str, Any]] = None) -> bool:
        sets = []; params: List[Any] = []
        if text is not None: sets.append("text=?"); params.append(text)
        if raw_text is not None: sets.append("raw_text=?"); params.append(raw_text)
        if status is not None: sets.append("status=?"); params.append(status)
        if due_at is not None or due_at is None:
            sets.append("due_at=?"); params.append(self._to_epoch(due_at))
        if source is not None: sets.append("source=?"); params.append(source)
        if source_agent is not None: sets.append("source_agent=?"); params.append(source_agent)
        if extra is not None: sets.append("extra=?"); params.append(json.dumps(extra, ensure_ascii=False))
        sets.append("updated_at=?"); params.append(self._now_epoch())
        params.append(task_id)
        if not sets:
            return False
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?;", params)
            return cur.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM tasks WHERE id=?;", (task_id,))
            return cur.rowcount > 0

    def list_upcoming_tasks(self, *, user_id: Optional[int] = None,
                            due_from: Optional[Union[int, float]] = None,
                            due_to: Optional[Union[int, float]] = None,
                            status: str = "open", limit: Optional[int] = None) -> List[Task]:
        df = self._to_epoch(due_from) or self._now_epoch()
        dt = self._to_epoch(due_to)
        clauses = ["status=?", "due_at IS NOT NULL", "due_at >= ?"]
        params: List[Any] = [status, df]
        if dt is not None:
            clauses.append("due_at <= ?"); params.append(dt)
        if user_id is not None:
            clauses.append("user_id=?"); params.append(user_id)
        where = "WHERE " + " AND ".join(clauses)
        lim = f" LIMIT {int(limit)}" if limit is not None else ""
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(f"""
                SELECT id, user_id, text, raw_text, status, due_at, created_at, updated_at, source, source_agent, extra
                FROM tasks {where} ORDER BY due_at ASC, id ASC {lim};
            """, params)
            rows = cur.fetchall()
            return [Task(id=r[0], user_id=r[1], text=r[2], raw_text=r[3], status=r[4],
                         due_at=r[5], created_at=r[6], updated_at=r[7],
                         source=r[8], source_agent=r[9], extra=self._loads_optional_json(r[10])) for r in rows]

    # ----- Notes -----
    def add_note(self, user_id: int, text: str, *, raw_text: Optional[str] = None,
                 source: Optional[str] = None, source_agent: Optional[str] = None,
                 extra: Optional[Dict[str, Any]] = None) -> int:
        created = updated = self._now_epoch()
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO notes (user_id, text, raw_text, created_at, updated_at, source, source_agent, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (user_id, text, raw_text, created, updated, source, source_agent, extra_json))
            return int(cur.lastrowid)

    def get_note(self, note_id: int) -> Optional[Note]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, user_id, text, raw_text, created_at, updated_at, source, source_agent, extra
                FROM notes WHERE id=?;
            """, (note_id,))
            r = cur.fetchone()
            if not r:
                return None
            return Note(id=r[0], user_id=r[1], text=r[2], raw_text=r[3],
                        created_at=r[4], updated_at=r[5], source=r[6],
                        source_agent=r[7], extra=self._loads_optional_json(r[8]))

    def list_notes(self, user_id: Optional[int] = None, *, order_by: str = "created_desc",
                   limit: Optional[int] = None, offset: int = 0) -> List[Note]:
        with self._connect() as con:
            cur = con.cursor()
            clauses = []; params: List[Any] = []
            if user_id is not None:
                clauses.append("user_id=?"); params.append(user_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            order_sql = "ORDER BY created_at DESC" if order_by == "created_desc" else "ORDER BY id ASC"
            lim = f" LIMIT {int(limit)}" if limit is not None else ""
            off = f" OFFSET {int(offset)}" if offset else ""
            cur.execute(f"""
                SELECT id, user_id, text, raw_text, created_at, updated_at, source, source_agent, extra
                FROM notes {where} {order_sql} {lim}{off};
            """, params)
            rows = cur.fetchall()
            return [Note(id=r[0], user_id=r[1], text=r[2], raw_text=r[3],
                         created_at=r[4], updated_at=r[5], source=r[6],
                         source_agent=r[7], extra=self._loads_optional_json(r[8])) for r in rows]

    def delete_note(self, note_id: int) -> bool:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM notes WHERE id=?;", (note_id,))
            return cur.rowcount > 0

    # ----- Maintenance -----
    def reset_db(self) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DROP TABLE IF EXISTS tasks;")
            cur.execute("DROP TABLE IF EXISTS notes;")
            cur.execute("DROP TABLE IF EXISTS schema_version;")
            con.execute("VACUUM;")
        self.init_db()

    def vacuum(self) -> None:
        with self._connect() as con:
            con.execute("VACUUM;")

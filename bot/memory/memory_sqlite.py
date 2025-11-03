# bot/memory/memory_sqlite.py
"""
Production-ready SQLite storage (только логику БД).
Без импортов Telegram/capture/handlers — чтобы исключить циклы.
Поддерживает двустороннюю синхронизацию с Google Calendar:
- расширенная схема tasks (calendar_id, calendar_event_id, etag, google_updated_at, recurrence, person_id, notes, last_modified)
- таблица oauth_tokens (провайдер, token_json, expiry и метаданные)
- безопасные миграции, индексы, удобные CRUD-методы.
"""

from __future__ import annotations

import sqlite3
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple
from contextlib import contextmanager

Epoch = int
# Увеличиваем версию схемы: 4 (ранее было 2 в твоём файле)
SCHEMA_VERSION = 4


# -------------------
# Dataclasses (DTO)
# -------------------

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
    # NEW
    calendar_id: Optional[str]                 # Google calendarId (можно хранить "primary" или явный id)
    calendar_event_id: Optional[str]           # Google event.id
    calendar_event_etag: Optional[str]         # Google event.etag для детекта изменений
    google_updated_at: Optional[Epoch]         # event.updated → epoch (UTC), для сравнения с локальным
    recurrence: Optional[str]                  # RRULE или простая метка ('yearly','monthly',...)
    person_id: Optional[int]                   # связь с человеком в Memory Graph (если есть)
    notes: Optional[str]                       # дополнительные заметки/контекст по событию
    last_modified: Epoch                       # локальная «истина» последнего изменения (UTC)


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


@dataclass
class OAuthToken:
    user_id: str
    provider: str                 # 'google_calendar'
    token_json: Dict[str, Any]    # сериализованный объект токена
    expiry: Optional[Epoch]       # момент истечения access_token (UTC)
    scopes: Optional[str]         # строка scopes (через пробел), опционально
    created_at: Epoch
    updated_at: Epoch


# -------------------
# Storage
# -------------------

class MemorySQLite:
    """
    SQLite-backed storage for tasks and notes + calendar sync + oauth tokens.
    """

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        self.db_path = str(db_path)
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
            # Надёжные параметры для продакшена (WAL + нормальный sync)
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA foreign_keys=ON;")
            con.execute("PRAGMA busy_timeout=3000;")
            yield con
        finally:
            con.close()

    # -------------------
    # Init & Migrations
    # -------------------

    def init_db(self) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );
            """)
            cur.execute("SELECT COUNT(*) FROM schema_version;")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO schema_version(version) VALUES (0);")

            # base tables
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

            # tokens table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    token_json TEXT NOT NULL,
                    expiry INTEGER,
                    scopes TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, provider)
                );
            """)

            self._migrate(con)
            self._ensure_indexes(con)

    def _ensure_indexes(self, con: sqlite3.Connection) -> None:
        cur = con.cursor()
        # tasks indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_at ON tasks(due_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_due ON tasks(user_id, due_at);")
        # NEW: calendar-related
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_calendar_link ON tasks(user_id, calendar_id, calendar_event_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_last_modified ON tasks(last_modified);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_google_updated ON tasks(google_updated_at);")
        # oauth indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_oauth_provider ON oauth_tokens(provider);")

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
        """
        Акуратно добавляем недостающие столбцы для продакшен-синхронизации календаря.
        """
        current = self._get_version(con)

        # v1: due_at
        if not self._column_exists(con, "tasks", "due_at"):
            con.execute("ALTER TABLE tasks ADD COLUMN due_at INTEGER;")
            current = max(current, 1)

        # v3: calendar & recurrence fields (пропускаем v2 как исторический)
        columns_to_add: List[Tuple[str, str]] = []
        if not self._column_exists(con, "tasks", "calendar_id"):
            columns_to_add.append(("calendar_id", "TEXT"))
        if not self._column_exists(con, "tasks", "calendar_event_id"):
            columns_to_add.append(("calendar_event_id", "TEXT"))
        if not self._column_exists(con, "tasks", "calendar_event_etag"):
            columns_to_add.append(("calendar_event_etag", "TEXT"))
        if not self._column_exists(con, "tasks", "google_updated_at"):
            columns_to_add.append(("google_updated_at", "INTEGER"))
        if not self._column_exists(con, "tasks", "recurrence"):
            columns_to_add.append(("recurrence", "TEXT"))
        if not self._column_exists(con, "tasks", "person_id"):
            columns_to_add.append(("person_id", "INTEGER"))
        if not self._column_exists(con, "tasks", "notes"):
            columns_to_add.append(("notes", "TEXT"))
        if not self._column_exists(con, "tasks", "last_modified"):
            columns_to_add.append(("last_modified", "INTEGER"))

        for col, typ in columns_to_add:
            con.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typ};")

        if columns_to_add:
            # Инициализируем last_modified для существующих строк значением updated_at
            if any(col == "last_modified" for col, _ in columns_to_add):
                con.execute("UPDATE tasks SET last_modified = COALESCE(updated_at, strftime('%s','now'));")
            current = max(current, 3)

        # v4: oauth_tokens уже создавалась выше через IF NOT EXISTS, а тут просто фиксируем версию
        if current < SCHEMA_VERSION:
            self._set_version(con, SCHEMA_VERSION)

    # -------------------
    # Utils
    # -------------------

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

    @staticmethod
    def _dumps_optional_json(obj: Optional[Dict[str, Any]]) -> Optional[str]:
        if obj is None:
            return None
        return json.dumps(obj, ensure_ascii=False)

    # -------------------
    # Tasks CRUD
    # -------------------

    def add_task(
        self,
        user_id: int,
        text: str,
        *,
        raw_text: Optional[str] = None,
        due_at: Optional[Union[int, float]] = None,
        status: str = "open",
        source: Optional[str] = None,
        source_agent: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        # NEW
        recurrence: Optional[str] = None,
        person_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        created = updated = self._now_epoch()
        due = self._to_epoch(due_at)
        extra_json = self._dumps_optional_json(extra)
        last_modified = updated  # локальная истина изменения
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO tasks (
                    user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id, text, raw_text, status, due, created, updated,
                    source, source_agent, extra_json,
                    None, None, None, None,
                    recurrence, person_id, notes, last_modified,
                ),
            )
            return int(cur.lastrowid)

    def _task_from_row(self, r: sqlite3.Row) -> Task:
        return Task(
            id=r[0], user_id=r[1], text=r[2], raw_text=r[3], status=r[4],
            due_at=r[5], created_at=r[6], updated_at=r[7],
            source=r[8], source_agent=r[9], extra=self._loads_optional_json(r[10]),
            calendar_id=r[11], calendar_event_id=r[12], calendar_event_etag=r[13],
            google_updated_at=r[14], recurrence=r[15], person_id=r[16], notes=r[17],
            last_modified=r[18],
        )

    def get_task(self, task_id: int) -> Optional[Task]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT
                    id, user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                FROM tasks WHERE id=?;
                """,
                (task_id,),
            )
            r = cur.fetchone()
            return self._task_from_row(r) if r else None

    def list_tasks(
        self,
        user_id: Optional[int] = None,
        *,
        status: Optional[str] = None,
        order_by: str = "due_at_nulls_last",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Task]:
        with self._connect() as con:
            cur = con.cursor()
            clauses: List[str] = []
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
            cur.execute(
                f"""
                SELECT
                    id, user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                FROM tasks {where} {order_sql} {lim}{off};
                """,
                params,
            )
            rows = cur.fetchall()
            return [self._task_from_row(r) for r in rows]

    def update_task(
        self,
        task_id: int,
        *,
        text: Optional[str] = None,
        raw_text: Optional[str] = None,
        status: Optional[str] = None,
        due_at: Optional[Union[int, float, None]] = None,
        source: Optional[str] = None,
        source_agent: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        recurrence: Optional[str] = None,
        person_id: Optional[int] = None,
        notes: Optional[str] = None,
        touch_last_modified: bool = True,
    ) -> bool:
        sets: List[str] = []
        params: List[Any] = []
        if text is not None: sets.append("text=?"); params.append(text)
        if raw_text is not None: sets.append("raw_text=?"); params.append(raw_text)
        if status is not None: sets.append("status=?"); params.append(status)
        if due_at is not None or due_at is None:
            sets.append("due_at=?"); params.append(self._to_epoch(due_at))
        if source is not None: sets.append("source=?"); params.append(source)
        if source_agent is not None: sets.append("source_agent=?"); params.append(source_agent)
        if extra is not None: sets.append("extra=?"); params.append(self._dumps_optional_json(extra))
        if recurrence is not None: sets.append("recurrence=?"); params.append(recurrence)
        if person_id is not None: sets.append("person_id=?"); params.append(person_id)
        if notes is not None: sets.append("notes=?"); params.append(notes)

        sets.append("updated_at=?"); params.append(self._now_epoch())
        if touch_last_modified:
            sets.append("last_modified=?"); params.append(self._now_epoch())

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

    def list_upcoming_tasks(
        self,
        *,
        user_id: Optional[int] = None,
        due_from: Optional[Union[int, float]] = None,
        due_to: Optional[Union[int, float]] = None,
        status: str = "open",
        limit: Optional[int] = None,
    ) -> List[Task]:
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
            cur.execute(
                f"""
                SELECT
                    id, user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                FROM tasks {where} ORDER BY due_at ASC, id ASC {lim};
                """,
                params,
            )
            rows = cur.fetchall()
            return [self._task_from_row(r) for r in rows]

    # -------------------
    # Calendar linking & sync helpers
    # -------------------

    def set_task_calendar_link(
        self,
        task_id: int,
        *,
        calendar_id: Optional[str],
        event_id: Optional[str],
        event_etag: Optional[str] = None,
        google_updated_at: Optional[Union[int, float]] = None,
    ) -> bool:
        """
        Привязать локальную задачу к событию в Google Calendar.
        """
        sets = [
            "calendar_id=?",
            "calendar_event_id=?",
            "calendar_event_etag=?",
            "google_updated_at=?",
            "updated_at=?",
        ]
        params: List[Any] = [
            calendar_id,
            event_id,
            event_etag,
            self._to_epoch(google_updated_at),
            self._now_epoch(),
        ]
        # Привязка сама по себе не меняет локальную last_modified, это техническое действие:
        sql = f"UPDATE tasks SET {', '.join(sets)} WHERE id=?;"
        params.append(task_id)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(sql, params)
            return cur.rowcount > 0

    def clear_task_calendar_link(self, task_id: int) -> bool:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                UPDATE tasks
                SET calendar_id=NULL, calendar_event_id=NULL, calendar_event_etag=NULL,
                    google_updated_at=NULL, updated_at=?
                WHERE id=?;
                """,
                (self._now_epoch(), task_id),
            )
            return cur.rowcount > 0

    def get_task_by_calendar_event(
        self, user_id: int, calendar_id: str, event_id: str
    ) -> Optional[Task]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT
                    id, user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                FROM tasks
                WHERE user_id=? AND calendar_id=? AND calendar_event_id=?
                LIMIT 1;
                """,
                (user_id, calendar_id, event_id),
            )
            r = cur.fetchone()
            return self._task_from_row(r) if r else None

    def list_tasks_missing_calendar_link(self, user_id: int) -> List[Task]:
        """
        Локальные задачи без привязки к календарю (кандидаты на создание events.insert).
        """
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT
                    id, user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                FROM tasks
                WHERE user_id=? AND calendar_event_id IS NULL AND status='open';
                """,
                (user_id,),
            )
            return [self._task_from_row(r) for r in cur.fetchall()]

    def list_tasks_modified_since(self, ts_epoch: int, user_id: Optional[int] = None) -> List[Task]:
        """
        Локально изменённые задачи с момента ts_epoch (для push-обновлений в Google).
        """
        with self._connect() as con:
            cur = con.cursor()
            clauses = ["last_modified > ?"]
            params: List[Any] = [int(ts_epoch)]
            if user_id is not None:
                clauses.append("user_id=?"); params.append(user_id)
            where = "WHERE " + " AND ".join(clauses)
            cur.execute(
                f"""
                SELECT
                    id, user_id, text, raw_text, status, due_at, created_at, updated_at,
                    source, source_agent, extra,
                    calendar_id, calendar_event_id, calendar_event_etag, google_updated_at,
                    recurrence, person_id, notes, last_modified
                FROM tasks
                {where}
                ORDER BY last_modified ASC;
                """,
                params,
            )
            return [self._task_from_row(r) for r in cur.fetchall()]

    def mark_task_locally_modified(self, task_id: int) -> bool:
        """
        Явно отметить локальное изменение (например, после «перенести/отложить»)
        """
        now = self._now_epoch()
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE tasks SET updated_at=?, last_modified=? WHERE id=?;",
                (now, now, task_id),
            )
            return cur.rowcount > 0

    # -------------------
    # Notes
    # -------------------

    def add_note(
        self,
        user_id: int,
        text: str,
        *,
        raw_text: Optional[str] = None,
        source: Optional[str] = None,
        source_agent: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        created = updated = self._now_epoch()
        extra_json = self._dumps_optional_json(extra)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO notes (user_id, text, raw_text, created_at, updated_at, source, source_agent, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, text, raw_text, created, updated, source, source_agent, extra_json),
            )
            return int(cur.lastrowid)

    def get_note(self, note_id: int) -> Optional[Note]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, user_id, text, raw_text, created_at, updated_at, source, source_agent, extra
                FROM notes WHERE id=?;
                """,
                (note_id,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return Note(
                id=r[0], user_id=r[1], text=r[2], raw_text=r[3],
                created_at=r[4], updated_at=r[5], source=r[6],
                source_agent=r[7], extra=self._loads_optional_json(r[8]),
            )

    def list_notes(
        self,
        user_id: Optional[int] = None,
        *,
        order_by: str = "created_desc",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Note]:
        with self._connect() as con:
            cur = con.cursor()
            clauses = []; params: List[Any] = []
            if user_id is not None:
                clauses.append("user_id=?"); params.append(user_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            order_sql = "ORDER BY created_at DESC" if order_by == "created_desc" else "ORDER BY id ASC"
            lim = f" LIMIT {int(limit)}" if limit is not None else ""
            off = f" OFFSET {int(offset)}" if offset else ""
            cur.execute(
                f"""
                SELECT id, user_id, text, raw_text, created_at, updated_at, source, source_agent, extra
                FROM notes {where} {order_sql} {lim}{off};
                """,
                params,
            )
            rows = cur.fetchall()
            return [
                Note(
                    id=r[0], user_id=r[1], text=r[2], raw_text=r[3],
                    created_at=r[4], updated_at=r[5], source=r[6],
                    source_agent=r[7], extra=self._loads_optional_json(r[8]),
                )
                for r in rows
            ]

    def delete_note(self, note_id: int) -> bool:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM notes WHERE id=?;", (note_id,))
            return cur.rowcount > 0

    # -------------------
    # OAuth tokens
    # -------------------

    def upsert_oauth_token(
        self,
        user_id: str,
        provider: str,
        token_json: Dict[str, Any],
        *,
        expiry: Optional[Union[int, float]] = None,
        scopes: Optional[List[str]] = None,
    ) -> None:
        """
        Сохранить/обновить OAuth-токен.
        Хранится как JSON, expiry — epoch (UTC), scopes — строка (через пробел).
        """
        now = self._now_epoch()
        scopes_str = " ".join(scopes) if scopes else None
        token_blob = self._dumps_optional_json(token_json) or "{}"
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO oauth_tokens (user_id, provider, token_json, expiry, scopes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    token_json=excluded.token_json,
                    expiry=excluded.expiry,
                    scopes=excluded.scopes,
                    updated_at=excluded.updated_at;
                """,
                (user_id, provider, token_blob, self._to_epoch(expiry), scopes_str, now, now),
            )

    def get_oauth_token(self, user_id: str, provider: str) -> Optional[OAuthToken]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT user_id, provider, token_json, expiry, scopes, created_at, updated_at
                FROM oauth_tokens
                WHERE user_id=? AND provider=?
                LIMIT 1;
                """,
                (user_id, provider),
            )
            r = cur.fetchone()
            if not r:
                return None
            return OAuthToken(
                user_id=r[0],
                provider=r[1],
                token_json=json.loads(r[2]) if r[2] else {},
                expiry=r[3],
                scopes=r[4],
                created_at=r[5],
                updated_at=r[6],
            )

    def delete_oauth_token(self, user_id: str, provider: str) -> bool:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM oauth_tokens WHERE user_id=? AND provider=?;", (user_id, provider))
            return cur.rowcount > 0

    # -------------------
    # Maintenance
    # -------------------

    def reset_db(self) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DROP TABLE IF EXISTS tasks;")
            cur.execute("DROP TABLE IF EXISTS notes;")
            cur.execute("DROP TABLE IF EXISTS oauth_tokens;")
            cur.execute("DROP TABLE IF EXISTS schema_version;")
            con.execute("VACUUM;")
        self.init_db()

    def vacuum(self) -> None:
        with self._connect() as con:
            con.execute("VACUUM;")
# End of memory_sqlite.py
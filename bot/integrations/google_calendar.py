# bot/integrations/google_calendar.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from bot.core.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_OAUTH_SCOPES,
    GOOGLE_DEFAULT_CALENDAR_ID,
    TZ,
    SYNC_WINDOW_DAYS,
)

# Ненавязчивые дефолты
_EVENT_DEFAULT_DURATION_MIN = 60
_EVENT_REMINDERS_MINUTES = [60]  # напоминание в Google (параллельно с ботом)


@dataclass
class _GEventLink:
    calendar_id: str
    event_id: str
    etag: Optional[str]
    google_updated_epoch: Optional[int]


def _epoch_to_rfc3339(epoch: int, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    return datetime.fromtimestamp(int(epoch), tz=tz).isoformat()


def _epoch_to_all_day_date(epoch: int, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    return datetime.fromtimestamp(int(epoch), tz=tz).date().isoformat()


def _parse_recurrence(recurrence: Optional[str]) -> Optional[List[str]]:
    if not recurrence:
        return None
    r = recurrence.strip().upper()
    if r.startswith("RRULE:"):
        return [r]
    mapping = {
        "YEARLY": "RRULE:FREQ=YEARLY",
        "MONTHLY": "RRULE:FREQ=MONTHLY",
        "WEEKLY": "RRULE:FREQ=WEEKLY",
        "DAILY": "RRULE:FREQ=DAILY",
    }
    if r in mapping:
        return [mapping[r]]
    r_lower = recurrence.strip().lower()
    if r_lower in ("yearly", "annually"):
        return ["RRULE:FREQ=YEARLY"]
    if r_lower == "monthly":
        return ["RRULE:FREQ=MONTHLY"]
    if r_lower == "weekly":
        return ["RRULE:FREQ=WEEKLY"]
    if r_lower == "daily":
        return ["RRULE:FREQ=DAILY"]
    return None


class GoogleCalendarClient:
    """
    Работает ТОЛЬКО через токен в БД (офлайн-provisioning выполнен).
    db — твой MemoryBackend. Мы используем только публичные методы:
      add_task, get_task, list_tasks, update_task (если нет — fallback на update_task_status),
      и extra (JSON) как хранилище линков gcal.
    """

    def __init__(self, db: Any):
        self.db = db

    # ---- Сервис/креды ----

    def is_connected(self, user_id: int) -> bool:
        return self.db.get_oauth_token(str(user_id), "google_calendar") is not None

    def _load_credentials(self, user_id: int) -> Credentials:
        tok = self.db.get_oauth_token(str(user_id), "google_calendar")
        if not tok:
            raise RuntimeError("Google Calendar не подключён. Сначала выполните provisioning.")
        tj = tok.token_json
        creds = Credentials(
            token=tj.get("token"),
            refresh_token=tj.get("refresh_token"),
            token_uri=tj.get("token_uri"),
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=(tok.scopes.split() if tok.scopes else GOOGLE_OAUTH_SCOPES),
        )
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            new_blob = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
                "expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
            }
            self.db.upsert_oauth_token(
                user_id=str(user_id),
                provider="google_calendar",
                token_json=new_blob,
                expiry=new_blob.get("expiry"),
                scopes=creds.scopes,
            )
        return creds

    def _service(self, user_id: int):
        return build("calendar", "v3", credentials=self._load_credentials(user_id), cache_discovery=False)

    # ---- Вспомогательные: доступ к gcal-линку через extra ----

    @staticmethod
    def _get_gcal_link(extra: Optional[Dict[str, Any]]) -> Optional[_GEventLink]:
        if not extra:
            return None
        g = (extra or {}).get("gcal") or {}
        ev = g.get("event_id")
        if not ev:
            return None
        return _GEventLink(
            calendar_id=g.get("calendar_id") or GOOGLE_DEFAULT_CALENDAR_ID,
            event_id=ev,
            etag=g.get("etag"),
            google_updated_epoch=g.get("updated_epoch"),
        )

    @staticmethod
    def _set_gcal_link(extra: Optional[Dict[str, Any]], *, calendar_id: str, event_id: str,
                       etag: Optional[str], updated_epoch: Optional[int]) -> Dict[str, Any]:
        ex = dict(extra or {})
        ex["gcal"] = {
            "calendar_id": calendar_id,
            "event_id": event_id,
            "etag": etag,
            "updated_epoch": updated_epoch,
        }
        return ex

    # ---- Построение Google event body из локальной задачи ----

    def _build_event_body(self, task, tz_name: str) -> Dict[str, Any]:
        extra = getattr(task, "extra", None) or {}
        all_day = bool(extra.get("all_day")) or extra.get("is_birthday") is True

        summary = (task.text or "Event").strip()[:255]
        description_parts: List[str] = []
        if getattr(task, "raw_text", None):
            description_parts.append(task.raw_text.strip())
        description = "\n\n".join([p for p in description_parts if p])

        if task.due_at is None:
            start = {"date": datetime.now(ZoneInfo(tz_name)).date().isoformat()}
            end = {"date": (datetime.now(ZoneInfo(tz_name)).date() + timedelta(days=1)).isoformat()}
        elif all_day:
            date_str = _epoch_to_all_day_date(task.due_at, tz_name)
            start = {"date": date_str}
            end_date = (datetime.fromisoformat(date_str) + timedelta(days=1)).date().isoformat()
            end = {"date": end_date}
        else:
            start_dt = _epoch_to_rfc3339(task.due_at, tz_name)
            end_dt = _epoch_to_rfc3339(task.due_at + _EVENT_DEFAULT_DURATION_MIN * 60, tz_name)
            start = {"dateTime": start_dt, "timeZone": tz_name}
            end = {"dateTime": end_dt, "timeZone": tz_name}

        body: Dict[str, Any] = {
            "summary": summary,
            "start": start,
            "end": end,
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": m} for m in _EVENT_REMINDERS_MINUTES],
            },
        }
        rec = _parse_recurrence(getattr(task, "recurrence", None))
        if rec:
            body["recurrence"] = rec
        if description:
            body["description"] = description
        return body

    # ---- CRUD (локальные → Google) ----

    def create_event(self, user_id: int, task) -> str:
        service = self._service(user_id)
        calendar_id = getattr(task, "calendar_id", None) or GOOGLE_DEFAULT_CALENDAR_ID
        body = self._build_event_body(task, TZ)
        created = service.events().insert(calendarId=calendar_id, body=body).execute()
        event_id = created.get("id")
        etag = created.get("etag")
        updated = created.get("updated")
        google_updated_epoch = None
        if updated:
            try:
                google_updated_epoch = int(datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass

        new_extra = self._set_gcal_link(getattr(task, "extra", None),
                                        calendar_id=calendar_id, event_id=event_id,
                                        etag=etag, updated_epoch=google_updated_epoch)
        # Сохраняем линк в extra
        self._safe_update_task(task.id, extra=new_extra)
        return str(event_id)

    def update_event(self, user_id: int, task) -> None:
        link = self._get_gcal_link(getattr(task, "extra", None))
        if not link:
            self.create_event(user_id, task)
            return
        service = self._service(user_id)
        body = self._build_event_body(task, TZ)
        updated = service.events().patch(calendarId=link.calendar_id, eventId=link.event_id, body=body).execute()
        etag = updated.get("etag")
        upd = updated.get("updated")
        google_updated_epoch = None
        if upd:
            try:
                google_updated_epoch = int(datetime.fromisoformat(upd.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
        new_extra = self._set_gcal_link(getattr(task, "extra", None),
                                        calendar_id=link.calendar_id, event_id=link.event_id,
                                        etag=etag, updated_epoch=google_updated_epoch)
        self._safe_update_task(task.id, extra=new_extra)

    def delete_event(self, user_id: int, task) -> None:
        link = self._get_gcal_link(getattr(task, "extra", None))
        if not link:
            return
        service = self._service(user_id)
        try:
            service.events().delete(calendarId=link.calendar_id, eventId=link.event_id).execute()
        except Exception:
            pass
        # Чистим линк из extra
        extra = dict(getattr(task, "extra", None) or {})
        if "gcal" in extra:
            extra.pop("gcal", None)
            self._safe_update_task(task.id, extra=extra)

    # ---- PULL-SYNC (Google → локально) ----

    def sync_pull(self, user_id: int, *, window_days: int = SYNC_WINDOW_DAYS) -> Dict[str, List[int]]:
        """
        Импорт/обновление событий из Google в локальные задачи в окне [-window_days; +window_days].
        Возвращает {imported: [task_ids], updated: [task_ids]}.
        """
        if not self.is_connected(user_id):
            return {"imported": [], "updated": []}

        tz = ZoneInfo(TZ)
        now = datetime.now(tz)
        time_min = (now - timedelta(days=window_days)).isoformat()
        time_max = (now + timedelta(days=window_days)).isoformat()

        service = self._service(user_id)
        events: List[Dict[str, Any]] = []
        page_token = None
        while True:
            resp = service.events().list(
                calendarId=GOOGLE_DEFAULT_CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                showDeleted=False,
                orderBy="startTime",
                pageToken=page_token,
            ).execute()
            events.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # Локальные задачи пользователя (любой статус) — для поиска по extra.gcal.event_id
        local = self.db.list_tasks(user_id=user_id, status=None, limit=None, offset=0)

        def _find_local_by_event_id(ev_id: str) -> Optional[Any]:
            for t in local:
                link = self._get_gcal_link(getattr(t, "extra", None))
                if link and link.event_id == ev_id:
                    return t
            return None

        imported_ids: List[int] = []
        updated_ids: List[int] = []

        for ev in events:
            if ev.get("status") == "cancelled":
                # Если есть локальная связанная — можно пометить/очистить, но пока пропустим
                continue

            # summary/description
            summary = (ev.get("summary") or "Событие").strip()
            description = (ev.get("description") or "").strip()

            # start/due_at
            start = ev.get("start", {})
            all_day = False
            if "dateTime" in start:
                dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
                due_epoch = int(dt.timestamp())
            elif "date" in start:
                # all-day: date без времени (локаль пользователя)
                dt = datetime.fromisoformat(start["date"])  # YYYY-MM-DD
                dt_local = datetime(dt.year, dt.month, dt.day, tzinfo=tz)
                due_epoch = int(dt_local.timestamp())
                all_day = True
            else:
                # fallback: пропускаем непонятные
                continue

            # updated
            updated_epoch = None
            if ev.get("updated"):
                try:
                    updated_epoch = int(datetime.fromisoformat(ev["updated"].replace("Z", "+00:00")).timestamp())
                except Exception:
                    pass

            ev_id = ev.get("id")
            etag = ev.get("etag")
            link_payload = {
                "calendar_id": GOOGLE_DEFAULT_CALENDAR_ID,
                "event_id": ev_id,
                "etag": etag,
                "updated_epoch": updated_epoch,
            }

            # Есть ли локальная задача с этим event_id?
            t = _find_local_by_event_id(ev_id)

            if not t:
                # создаём новую локальную задачу
                extra = {"gcal": link_payload}
                if all_day:
                    extra["all_day"] = True
                task_id = self.db.add_task(
                    user_id=user_id,
                    text=summary,
                    raw_text=description or summary,
                    due_at=due_epoch,
                    extra=extra,
                )
                imported_ids.append(int(task_id))
                # добавляем в локальный кэш, чтобы искать дальше
                local.append(self.db.get_task(task_id))
                continue

            # Есть локальная — проверим, нужно ли обновить поле(я)
            needs_update = False
            new_text = t.text
            new_raw = t.raw_text
            new_due = t.due_at
            new_extra = dict(getattr(t, "extra", None) or {})
            new_extra["gcal"] = link_payload
            if all_day:
                new_extra["all_day"] = True

            if summary and summary != t.text:
                new_text = summary
                needs_update = True
            if description and description != (t.raw_text or ""):
                new_raw = description
                needs_update = True
            if due_epoch and due_epoch != (t.due_at or 0):
                new_due = due_epoch
                needs_update = True

            if needs_update:
                self._safe_update_task(t.id, text=new_text, raw_text=new_raw, due_at=new_due, extra=new_extra)
                updated_ids.append(int(t.id))
            else:
                # даже если не обновляли, линк держим консистентным
                self._safe_update_task(t.id, extra=new_extra)

        return {"imported": imported_ids, "updated": updated_ids}

    # ---- безопасное обновление (на случай, если адаптер не имеет update_task) ----

    def _safe_update_task(self, task_id: int, **fields) -> None:
        """
        Пробует db.update_task(...). Если в адаптере только update_task_status — тихо пропустит.
        """
        try:
            # type: ignore[attr-defined]
            self.db.update_task(task_id, **fields)
        except AttributeError:
            # как минимум статус мы менять не будем; для совместимости — игнор
            pass

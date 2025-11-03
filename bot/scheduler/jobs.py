# bot/scheduler/jobs.py
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, List

from apscheduler.triggers.cron import CronTrigger

from bot.core.config import (
    TZ, BACKUP_DIR, BACKUP_TIME, BACKUP_KEEP_DAYS,
    DB_PATH, JOBSTORE_DB_PATH, INSTANCE_NAME,
)
from bot.integrations.google_calendar import GoogleCalendarClient
from bot.commands.task_actions import build_task_actions_kb

logger = logging.getLogger(__name__)

# ---------- общие утилиты ----------

async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def safe_job(name: str):
    """
    Декоратор для безопасного исполнения фоновых задач.
    Ловит исключения и логирует их, чтобы планировщик не падал.
    """
    def _wrap(coro):
        async def _inner(*args, **kwargs):
            try:
                return await coro(*args, **kwargs)
            except Exception as e:
                logger.exception("❌ Job '%s' failed: %s", name, e)
        return _inner
    return _wrap


# ---------- Напоминание по задаче ----------

@safe_job("send_task_reminder")
async def send_task_reminder(app, _mem, user_id: int, task_id: int) -> None:
    t = await _run_blocking(_mem.get_task, task_id)
    if not t or not t.due_at:
        return
    chat_id = user_id
    when = datetime.fromtimestamp(t.due_at, tz=ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M")
    suffix = " (весь день)" if (getattr(t, "extra", None) or {}).get("all_day") else ""
    text = f"⏰ Напоминание: {t.text}{suffix}\nВремя: {when}"
    try:
        await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.warning("send_task_reminder: failed to send message", exc_info=True)


# ---------- План на завтра ----------

@safe_job("send_daily_digest")
async def send_daily_digest(app, _mem, user_id: int) -> None:
    tz = ZoneInfo(TZ)
    now = datetime.now(tz)
    start = datetime(now.year, now.month, now.day, tzinfo=tz) + timedelta(days=1)
    end = start + timedelta(days=1)

    upcoming = await _run_blocking(
        _mem.list_upcoming_tasks,
        user_id=user_id,
        due_from=int(start.timestamp()),
        due_to=int(end.timestamp()),
        status="open",
        limit=100,
    )
    if not upcoming:
        return

    lines: List[str] = ["🗓 План на завтра:"]
    for t in upcoming:
        when = datetime.fromtimestamp(t.due_at, tz=tz).strftime("%H:%M") if t.due_at else "—"
        lines.append(f"🕒 [{t.id}] {t.text} — {when}")
    try:
        await app.bot.send_message(chat_id=user_id, text="\n".join(lines))
    except Exception:
        logger.warning("send_daily_digest: failed to send message", exc_info=True)


# ---------- Просроченные задачи с кнопками ----------

@safe_job("send_overdue_digest")
async def send_overdue_digest(app, _mem, user_id: int) -> None:
    tz = ZoneInfo(TZ)
    now_epoch = int(datetime.now(tz).timestamp())

    items = await _run_blocking(
        _mem.list_upcoming_tasks, user_id=user_id,
        due_from=0, due_to=now_epoch - 1, status="open", limit=100
    )
    if not items:
        return

    try:
        await app.bot.send_message(chat_id=user_id, text="⚠️ Просроченные задачи:")
    except Exception:
        logger.warning("send_overdue_digest: header send failed", exc_info=True)

    for t in items:
        when = datetime.fromtimestamp(t.due_at, tz=tz).strftime("%Y-%m-%d %H:%M") if t.due_at else "—"
        text = f"• [{t.id}] {t.text}\n⏳ Срок был: {when}"
        kb = build_task_actions_kb(t.id)
        try:
            await app.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
        except Exception:
            logger.warning("send_overdue_digest: item send failed", exc_info=True)


# ---------- Pull-sync Google + постановка напоминаний ----------

@safe_job("run_google_pull_and_schedule")
async def run_google_pull_and_schedule(app, _mem, user_id: int, scheduler) -> None:
    gc = GoogleCalendarClient(_mem)
    if not gc.is_connected(user_id):
        return
    res = await _run_blocking(gc.sync_pull, user_id)
    tz = ZoneInfo(TZ)

    affected_ids = list(set(res.get("imported", []) + res.get("updated", [])))
    now = datetime.now(tz).timestamp()
    for task_id in affected_ids:
        t = await _run_blocking(_mem.get_task, task_id)
        if not t or not t.due_at:
            continue
        is_all_day = (getattr(t, "extra", None) or {}).get("all_day") is True
        if is_all_day:
            continue
        when_epoch = int(t.due_at) - 3600
        if when_epoch <= now:
            continue
        run_date = datetime.fromtimestamp(when_epoch, tz=tz)
        try:
            scheduler.add_job(
                send_task_reminder,
                trigger="date",
                run_date=run_date,
                args=[app, _mem, user_id, int(task_id)],
                id=f"reminder:{user_id}:{task_id}",
                replace_existing=True,
            )
        except Exception:
            logger.warning("schedule reminder failed for task_id=%s", task_id, exc_info=True)


# ---------- Health ping (в лог и по желанию — владельцу) ----------

@safe_job("health_ping")
async def health_ping(app, _mem, user_id: int, scheduler) -> None:
    try:
        jobs = scheduler.get_jobs()
        info_lines = [
            f"💚 HEALTH [{INSTANCE_NAME}]",
            f"Jobs: {len(jobs)}",
        ]
        for j in jobs[:10]:
            next_run = j.next_run_time.isoformat() if j.next_run_time else "—"
            info_lines.append(f" - {j.id} → {next_run}")
        logger.info("\n".join(info_lines))
        # при желании — слать владельцу раз в N часов: закомментировано
        # await app.bot.send_message(chat_id=user_id, text="\n".join(info_lines))
    except Exception:
        logger.warning("health_ping failed", exc_info=True)


# ---------- Бэкап SQLite ----------

def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def _rotate_old_backups(prefix: str, keep_days: int) -> None:
    """
    Удаляем бэкапы старше keep_days по префиксу имени.
    """
    try:
        import os, time, glob
        cutoff = time.time() - keep_days * 86400
        for path in glob.glob(str(BACKUP_DIR / f"{prefix}-*.zip")):
            if os.path.getmtime(path) < cutoff:
                try:
                    os.remove(path)
                except Exception:
                    logger.warning("cannot remove old backup: %s", path, exc_info=True)
    except Exception:
        logger.warning("rotate backups failed", exc_info=True)

@safe_job("sqlite_backup_job")
async def sqlite_backup_job() -> None:
    """
    Делаем zip-бэкап двух БД: основной и jobstore.
    Храним в BACKUP_DIR с ротацией старше BACKUP_KEEP_DAYS.
    """
    try:
        import zipfile
        stamp = _timestamp()
        out = BACKUP_DIR / f"{INSTANCE_NAME}-{stamp}.zip"
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Основная БД
            try:
                tmp1 = BACKUP_DIR / f"_tmp_{stamp}_app.sqlite3"
                shutil.copy2(DB_PATH, tmp1)
                zf.write(tmp1, arcname="app.sqlite3")
                tmp1.unlink(missing_ok=True)
            except Exception:
                logger.warning("backup: app.sqlite3 copy failed", exc_info=True)

            # Jobstore
            try:
                tmp2 = BACKUP_DIR / f"_tmp_{stamp}_jobs.sqlite3"
                shutil.copy2(JOBSTORE_DB_PATH, tmp2)
                zf.write(tmp2, arcname="jobs.sqlite3")
                tmp2.unlink(missing_ok=True)
            except Exception:
                logger.warning("backup: jobs.sqlite3 copy failed", exc_info=True)

        _rotate_old_backups(INSTANCE_NAME, BACKUP_KEEP_DAYS)
        logger.info("💾 Backup created: %s", out)
    except Exception:
        logger.exception("sqlite_backup_job failed")

def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    try:
        hh, mm = hhmm.split(":")
        return int(hh), int(mm)
    except Exception:
        return 2, 30  # дефолт

def schedule_sqlite_backup_job(sched) -> None:
    hh, mm = _parse_hhmm(BACKUP_TIME)
    sched.add_job(
        sqlite_backup_job,
        trigger=CronTrigger(hour=hh, minute=mm),
        id="sqlite_backup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

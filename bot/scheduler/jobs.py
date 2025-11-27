from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, List

from apscheduler.triggers.cron import CronTrigger

from bot.core.config import (
    TZ,
    BACKUP_DIR,
    BACKUP_TIME,
    BACKUP_KEEP_DAYS,
    DB_PATH,
    JOBSTORE_DB_PATH,
    INSTANCE_NAME,
)
from bot.integrations.google_calendar import GoogleCalendarClient
from bot.commands.task_actions import build_task_actions_kb

logger = logging.getLogger(__name__)


# ----------------------- Утилиты -----------------------


async def _run_blocking(func, *args, **kwargs):
    """
    Запустить блокирующую функцию в thread pool из async-кода.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# ----------------------- Напоминания -----------------------


async def send_task_reminder(app, _mem, user_id: int, task_id: int) -> None:
    """
    Разовое напоминание по задаче.
    Отправляет текст + те же кнопки действий, что и в списках задач.
    """
    try:
        t = await _run_blocking(_mem.get_task, task_id)
        if not t or not t.due_at:
            return

        chat_id = user_id
        tz = ZoneInfo(TZ)
        when = datetime.fromtimestamp(t.due_at, tz=tz).strftime("%Y-%m-%d %H:%M")
        suffix = " (весь день)" if (getattr(t, "extra", None) or {}).get("all_day") else ""
        text = f"⏰ Напоминание: {t.text}{suffix}\nВремя: {when}"

        await app.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=build_task_actions_kb(t.id),
        )
    except Exception:
        logger.exception("send_task_reminder: failed")



# ----------------------- Утренний брифинг -----------------------


async def morning_briefing(app, _mem, user_id: int) -> None:
    """
    08:00 — показать краткий план на сегодня карточками с кнопками действий.
    """
    try:
        tz = ZoneInfo(TZ)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        upcoming = await _run_blocking(
            _mem.list_upcoming_tasks,
            user_id=user_id,
            due_from=int(start.timestamp()),
            due_to=int(end.timestamp()),
            status="open",
            limit=50,
        )

        if not upcoming:
            await app.bot.send_message(
                chat_id=user_id,
                text="🌅 Доброе утро!\nНа сегодня задач нет. Отличного дня! 👌",
            )
            return

        # Шапка-обзор
        await app.bot.send_message(
            chat_id=user_id,
            text=f"🌅 Доброе утро!\nВот твои задачи на сегодня ({len(upcoming)}):",
        )

        # Карточки по задачам с action-кнопками
        for t in upcoming:
            when = (
                datetime.fromtimestamp(t.due_at, tz=tz).strftime("%H:%M")
                if t.due_at
                else "—"
            )
            caption = f"🕒 {when} — {t.text}\n[id: {t.id}]"
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=caption,
                    reply_markup=build_task_actions_kb(t.id),
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.warning("morning_briefing: failed to send task id=%s", t.id, exc_info=True)

    except Exception:
        logger.exception("morning_briefing failed")



# ----------------------- План на завтра (сырые задачи) -----------------------


async def send_daily_digest(app, _mem, user_id: int) -> None:
    """
    Вечерний дайджест задач на завтра (карточками с кнопками действий).
    """
    try:
        tz = ZoneInfo(TZ)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
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
            # если на завтра ничего нет — можно молча промолчать
            return

        date_label = start.strftime("%Y-%m-%d")
        await app.bot.send_message(
            chat_id=user_id,
            text=f"🗓 План на завтра ({date_label}) — {len(upcoming)} задач(и):",
        )

        for t in upcoming:
            when = (
                datetime.fromtimestamp(t.due_at, tz=tz).strftime("%H:%M")
                if t.due_at
                else "—"
            )
            caption = f"🕒 {when} — {t.text}\n[id: {t.id}]"
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=caption,
                    reply_markup=build_task_actions_kb(t.id),
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.warning("send_daily_digest: failed to send task id=%s", t.id, exc_info=True)

    except Exception:
        logger.exception("send_daily_digest failed")



# ----------------------- Просроченные задачи -----------------------


async def send_overdue_digest(app, _mem, user_id: int) -> None:
    """
    Вечерний дайджест просроченных задач.
    """
    try:
        tz = ZoneInfo(TZ)
        now_epoch = int(datetime.now(tz).timestamp())

        items = await _run_blocking(
            _mem.list_upcoming_tasks,
            user_id=user_id,
            due_from=0,
            due_to=now_epoch - 1,
            status="open",
            limit=100,
        )
        if not items:
            return

        await app.bot.send_message(chat_id=user_id, text="⚠️ Просроченные задачи:")

        for t in items:
            when = (
                datetime.fromtimestamp(t.due_at, tz=tz).strftime("%Y-%m-%d %H:%M")
                if t.due_at
                else "—"
            )
            text = f"• [{t.id}] {t.text}\n⏳ Срок был: {when}"
            kb = build_task_actions_kb(t.id)
            try:
                await app.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
            except Exception:
                logger.warning("send_overdue_digest: item send failed", exc_info=True)
    except Exception:
        logger.exception("send_overdue_digest failed")


# ----------------------- Google Pull + Напоминания -----------------------


async def run_google_pull_and_schedule(app, _mem, user_id: int, scheduler) -> None:
    """
    Пулл-синк из Google Calendar + постановка напоминаний.
    """
    try:
        gc = GoogleCalendarClient(_mem)
        if not gc.is_connected(user_id):
            return

        tz = ZoneInfo(TZ)
        res = await _run_blocking(gc.sync_pull, user_id)
        affected_ids = list(set(res.get("imported", []) + res.get("updated", [])))
        now = datetime.now(tz).timestamp()

        for task_id in affected_ids:
            t = await _run_blocking(_mem.get_task, task_id)
            if not t or not t.due_at:
                continue
            if (getattr(t, "extra", None) or {}).get("all_day"):
                continue

            when_epoch = int(t.due_at) - 3600  # за час до события
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
                logger.warning(
                    "schedule reminder failed for task_id=%s", task_id, exc_info=True
                )
    except Exception:
        logger.exception("run_google_pull_and_schedule failed")


# ----------------------- Health ping -----------------------


async def health_ping(app, _mem, user_id: int, scheduler) -> None:
    """
    Периодический health-пинг: логируем состояние джобов.
    """
    try:
        jobs = scheduler.get_jobs()
        info_lines = [f"💚 HEALTH [{INSTANCE_NAME}]", f"Jobs: {len(jobs)}"]
        for j in jobs[:10]:
            nxt = j.next_run_time.isoformat() if j.next_run_time else "—"
            info_lines.append(f" - {j.id} → {nxt}")
        logger.info("\n".join(info_lines))
    except Exception:
        logger.warning("health_ping failed", exc_info=True)


# ----------------------- Бэкап SQLite -----------------------


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _rotate_old_backups(prefix: str, keep_days: int) -> None:
    try:
        import os
        import time
        import glob

        cutoff = time.time() - keep_days * 86400
        for path in glob.glob(str(BACKUP_DIR / f"{prefix}-*.zip")):
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
    except Exception:
        logger.warning("rotate backups failed", exc_info=True)


async def sqlite_backup_job() -> None:
    """
    Ночной бэкап app.sqlite3 + jobs.sqlite3 в ZIP.
    """
    try:
        import zipfile

        stamp = _timestamp()
        out = BACKUP_DIR / f"{INSTANCE_NAME}-{stamp}.zip"
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src, name in [
                (DB_PATH, "app.sqlite3"),
                (JOBSTORE_DB_PATH, "jobs.sqlite3"),
            ]:
                try:
                    tmp = BACKUP_DIR / f"_tmp_{stamp}_{name}"
                    shutil.copy2(src, tmp)
                    zf.write(tmp, arcname=name)
                    tmp.unlink(missing_ok=True)
                except Exception:
                    logger.warning(
                        "backup copy failed: %s", name, exc_info=True
                    )

        _rotate_old_backups(INSTANCE_NAME, BACKUP_KEEP_DAYS)
        logger.info("💾 Backup created: %s", out)
    except Exception:
        logger.exception("sqlite_backup_job failed")


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    try:
        hh, mm = hhmm.split(":")
        return int(hh), int(mm)
    except Exception:
        return 2, 30


def schedule_sqlite_backup_job(sched) -> None:
    """
    Регистрирует cron-задачу на ежедневный бэкап.
    """
    hh, mm = _parse_hhmm(BACKUP_TIME)
    sched.add_job(
        sqlite_backup_job,
        trigger=CronTrigger(hour=hh, minute=mm),
        id="sqlite_backup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("💾 SQLite backup job scheduled at %02d:%02d daily", hh, mm)

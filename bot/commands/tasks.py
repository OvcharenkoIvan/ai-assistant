# bot/commands/tasks.py
from telegram import Update
from telegram.ext import ContextTypes
from bot.memory.memory_loader import get_memory
from bot.core.logger import log_action
from functools import partial

# Singleton memory instance
_mem = get_memory()


async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Добавляет новую задачу для пользователя.
    Команда: /task <текст>
    """
    user_id = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("⚠️ Укажи текст задачи: /task <текст>")
        return

    task_id = await _mem.add_task(user_id=user_id, text=text)
    log_action(f"User {user_id} добавил задачу (id={task_id}): {text}")
    await update.message.reply_text("✅ Задача сохранена!")


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Выводит список открытых задач пользователя.
    Команда: /tasks
    """
    user_id = update.effective_user.id
    tasks_list = await _mem.list_tasks(user_id=user_id, status="open")
    if not tasks_list:
        await update.message.reply_text("📭 Нет открытых задач.")
        return

    msg = "\n".join(f"{i+1}. {t.text}" for i, t in enumerate(tasks_list[:20]))
    if len(tasks_list) > 20:
        msg += f"\n\n⚠️ Показаны первые 20 из {len(tasks_list)}"
    await update.message.reply_text("📝 Твои задачи:\n" + msg)


async def reset_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Удаляет все задачи пользователя.
    Команда: /reset_tasks
    """
    user_id = update.effective_user.id
    tasks_list = await _mem.list_tasks(user_id=user_id)
    for t in tasks_list:
        await _mem.delete_task(t.id)
    log_action(f"User {user_id} удалил все задачи")
    await update.message.reply_text("🗑 Все задачи удалены.")


async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отмечает задачу как выполненную.
    Команда: /complete <номер>
    """
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("⚠️ Укажи номер задачи для завершения: /complete <номер>")
        return

    try:
        task_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Номер задачи должен быть числом.")
        return

    tasks_list = await _mem.list_tasks(user_id=user_id, status="open")
    if task_num < 1 or task_num > len(tasks_list):
        await update.message.reply_text("⚠️ Неверный номер задачи.")
        return

    task = tasks_list[task_num - 1]
    await _mem.update_task(task.id, status="done")
    log_action(f"User {user_id} завершил задачу: {task.text}")
    await update.message.reply_text(f"✅ Задача '{task.text}' отмечена как выполненная.")

#!/usr/bin/env python3
"""Telegram bot for task management. Runs as a long-lived process.

Commands:
  /add <description>          — add task to inbox
  /add <description> @client  — add to specific project
  /done <search>              — mark task as done
  /list                       — show all open tasks
  /urgent                     — show urgent tasks only
  /daily                      — generate & send today's daily list
  /board                      — regenerate the board
  (any plain text)            — quick-add to inbox
"""

import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Add task-cli to path
sys.path.insert(0, str(Path(__file__).parent))

from parser import (
    TASKS_DIR,
    Task,
    add_task_to_file,
    client_to_filename,
    complete_task,
    ensure_structure,
    load_config,
    parse_date,
    read_all_tasks,
    task_to_line,
)

from board import generate_board

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def refresh_board():
    """Regenerate the HTML board after any task change."""
    try:
        generate_board(TASKS_DIR)
    except Exception:
        pass

config = load_config()
ALLOWED_CHAT_ID = config.get("telegram", {}).get("chat_id")


def auth(func):
    """Only allow the configured chat ID."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != ALLOWED_CHAT_ID:
            await update.message.reply_text("Not authorized.")
            return
        return await func(update, context)
    return wrapper


@auth
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /add <task description>\nOptional: @clientname @urgent @due(friday) @effort(2h)")
        return

    # Parse inline tags from the message
    import re
    from parser import TAG_RE

    tags = {}
    for m in TAG_RE.finditer(text):
        tags[m.group(1).lower()] = m.group(2)
    description = TAG_RE.sub("", text).strip()

    task = Task(
        description=description,
        done=False,
        due=parse_date(tags["due"]) if "due" in tags else None,
        urgent="urgent" in tags,
        effort=tags.get("effort"),
    )
    line = task_to_line(task)

    # Check for client tag (standalone @word that isn't a known tag)
    client_match = re.findall(r"@(\w+)(?!\()", text)
    client = None
    for c in client_match:
        if c.lower() not in ("urgent", "due", "effort", "done"):
            client = c
            break

    if client:
        filepath = TASKS_DIR / client_to_filename(client)
    else:
        filepath = TASKS_DIR / "inbox.md"

    add_task_to_file(filepath, line)
    refresh_board()
    target = filepath.stem.replace("-", " ").title()
    await update.message.reply_text(f"Added to {target}: {description}")


@auth
async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search = " ".join(context.args) if context.args else ""
    if not search:
        await update.message.reply_text("Usage: /done <search term>")
        return

    tasks = read_all_tasks()
    open_tasks = [t for t in tasks if not t.done]
    search_lower = search.lower()
    matches = [t for t in open_tasks if search_lower in t.description.lower()]

    if not matches:
        await update.message.reply_text(f"No open tasks matching '{search}'.")
        return

    if len(matches) == 1:
        target = matches[0]
        complete_task(Path(target.source_file), target.line_number)
        refresh_board()
        await update.message.reply_text(f"Done: {target.description}")
    else:
        lines = [f"{i+1}. {t.description} ({Path(t.source_file).stem.replace('-', ' ').title()})"
                 for i, t in enumerate(matches[:10])]
        await update.message.reply_text(
            f"Multiple matches:\n\n" + "\n".join(lines) + "\n\nBe more specific with /done"
        )


@auth
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = read_all_tasks()
    open_tasks = [t for t in tasks if not t.done]

    if not open_tasks:
        await update.message.reply_text("No open tasks!")
        return

    grouped: dict[str, list[Task]] = {}
    for t in open_tasks:
        name = Path(t.source_file).stem.replace("-", " ").title()
        grouped.setdefault(name, []).append(t)

    lines = []
    for project, group in sorted(grouped.items()):
        lines.append(f"\n*{project}*")
        for t in group:
            prefix = "🔴 " if t.is_overdue else ("🟡 " if t.urgent else "")
            due = f" (due {t.due})" if t.due else ""
            effort = f" [{t.effort}]" if t.effort else ""
            lines.append(f"  {prefix}▫️ {t.description}{due}{effort}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@auth
async def cmd_urgent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = read_all_tasks()
    urgent = [t for t in tasks if not t.done and (t.urgent or t.is_overdue)]

    if not urgent:
        await update.message.reply_text("No urgent tasks!")
        return

    lines = []
    for t in urgent:
        project = Path(t.source_file).stem.replace("-", " ").title()
        prefix = "🔴 " if t.is_overdue else "🟡 "
        lines.append(f"{prefix}{t.description} ({project})")

    await update.message.reply_text("\n".join(lines))


@auth
async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating daily list...")

    from ai import generate_daily
    hours = config.get("daily", {}).get("available_hours", 6)
    content = generate_daily(TASKS_DIR, available_hours=hours)

    daily_file = TASKS_DIR / "daily" / f"{date.today().isoformat()}.md"
    daily_file.write_text(content)

    await update.message.reply_text(content)


@auth
async def cmd_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    refresh_board()
    board_path = TASKS_DIR / "board.html"
    if board_path.exists():
        await update.message.reply_document(
            document=open(board_path, "rb"),
            filename="board.html",
            caption="Open in your browser for the full kanban view",
        )
    else:
        await update.message.reply_text("No board found.")


@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! I'm your task bot.\n\n"
        "/add <task> — add a task (use @client @urgent @due(fri))\n"
        "/done <search> — complete a task\n"
        "/list — all open tasks\n"
        "/urgent — urgent tasks only\n"
        "/daily — generate daily list\n\n"
        "Or just type anything to quick-add to inbox."
    )


@auth
async def plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Any non-command text gets added to inbox."""
    text = update.message.text.strip()
    if not text:
        return

    task = Task(description=text, done=False)
    line = task_to_line(task)
    add_task_to_file(TASKS_DIR / "inbox.md", line)
    refresh_board()
    await update.message.reply_text(f"Added to Inbox: {text}")


def main():
    ensure_structure()
    token = config.get("telegram", {}).get("token")
    if not token:
        print("Error: No telegram token in ~/.tasks/config.yaml")
        sys.exit(1)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("urgent", cmd_urgent))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("board", cmd_board))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()

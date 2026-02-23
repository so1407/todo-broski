#!/usr/bin/env python3
"""Telegram bot for task management. Runs as a long-lived process.

Just chat naturally:
  "add fix login bug for trewit, urgent"
  "done with the invoice"
  "what's on my list?"
  "show me urgent stuff"
  "daily"
  "board"

Slash commands still work too: /add /done /list /urgent /daily /board
"""

import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

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

config = load_config()
ALLOWED_CHAT_ID = config.get("telegram", {}).get("chat_id")
AI_MODEL = "claude-haiku-4-5-20251001"


def refresh_board():
    try:
        generate_board(TASKS_DIR)
    except Exception:
        pass


def get_ai_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY") or config.get("anthropic_api_key")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != ALLOWED_CHAT_ID:
            await update.message.reply_text("Not authorized.")
            return
        return await func(update, context)
    return wrapper


# ── Core actions (used by both commands and natural language) ─────────────

def action_add(description: str, client: str | None = None, due: str | None = None,
               urgent: bool = False, effort: str | None = None) -> str:
    task = Task(
        description=description,
        done=False,
        due=parse_date(due) if due else None,
        urgent=urgent,
        effort=effort,
    )
    line = task_to_line(task)

    if client:
        filepath = TASKS_DIR / client_to_filename(client)
    else:
        filepath = TASKS_DIR / "inbox.md"

    add_task_to_file(filepath, line)
    refresh_board()
    target = filepath.stem.replace("-", " ").title()
    return f"Added to {target}: {description}"


def action_done(search: str) -> str:
    tasks = read_all_tasks()
    open_tasks = [t for t in tasks if not t.done]
    search_lower = search.lower()
    matches = [t for t in open_tasks if search_lower in t.description.lower()]

    if not matches:
        return f"No open tasks matching '{search}'."

    if len(matches) == 1:
        target = matches[0]
        complete_task(Path(target.source_file), target.line_number)
        refresh_board()
        return f"✓ Done: {target.description}"

    lines = [f"{i+1}. {t.description} ({Path(t.source_file).stem.replace('-', ' ').title()})"
             for i, t in enumerate(matches[:10])]
    return "Multiple matches:\n\n" + "\n".join(lines) + "\n\nBe more specific."


def action_list(urgent_only: bool = False) -> str:
    tasks = read_all_tasks()
    open_tasks = [t for t in tasks if not t.done]

    if urgent_only:
        open_tasks = [t for t in open_tasks if t.urgent or t.is_overdue]

    if not open_tasks:
        return "No urgent tasks!" if urgent_only else "No open tasks!"

    grouped: dict[str, list[Task]] = {}
    for t in open_tasks:
        name = Path(t.source_file).stem.replace("-", " ").title()
        grouped.setdefault(name, []).append(t)

    lines = []
    for project, group in sorted(grouped.items()):
        lines.append(f"\n*{project}*")
        for t in group:
            prefix = "🔴 " if t.is_overdue else ("🟡 " if t.urgent else "")
            due_str = f" (due {t.due})" if t.due else ""
            effort_str = f" [{t.effort}]" if t.effort else ""
            lines.append(f"  {prefix}▫️ {t.description}{due_str}{effort_str}")

    return "\n".join(lines)


def action_daily() -> str:
    from ai import generate_daily
    hours = config.get("daily", {}).get("available_hours", 6)
    content = generate_daily(TASKS_DIR, available_hours=hours)
    daily_file = TASKS_DIR / "daily" / f"{date.today().isoformat()}.md"
    daily_file.write_text(content)
    return content


# ── Natural language handler ─────────────────────────────────────────────

def parse_with_ai(text: str) -> dict | None:
    """Use Claude to parse natural language into a structured action."""
    client = get_ai_client()
    if not client:
        return None

    # Build context about existing projects
    project_files = [f.stem.replace("-", " ").title()
                     for f in sorted(TASKS_DIR.glob("*.md"))
                     if f.name != "inbox.md"]

    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": text}],
        system=f"""You are a task bot parser. The user sends casual messages. Parse them into JSON actions.

Known projects: {', '.join(project_files) if project_files else 'none yet'}
Today: {date.today().isoformat()} ({date.today().strftime('%A')})

Respond with ONLY a JSON object, nothing else. Possible actions:

Add a task:
{{"action": "add", "description": "task text", "client": "project name or null", "due": "YYYY-MM-DD or null", "urgent": true/false, "effort": "2h or null"}}

Complete a task:
{{"action": "done", "search": "search term to match task"}}

List tasks:
{{"action": "list", "urgent_only": false}}

List urgent tasks:
{{"action": "list", "urgent_only": true}}

Generate daily list:
{{"action": "daily"}}

Show board:
{{"action": "board"}}

If the message is conversational or unclear:
{{"action": "unknown", "reply": "your friendly response asking for clarification"}}

Match client names fuzzily to known projects. If someone says "trewit" match to "Trewit", "pmu" to "Pmu" etc.
For "done" actions, extract the most distinctive keyword from what they describe to use as search term.""",
    )

    try:
        result_text = response.content[0].text.strip()
        # Handle markdown code blocks
        if result_text.startswith("```"):
            result_text = re.sub(r"^```\w*\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)
        return json.loads(result_text)
    except (json.JSONDecodeError, IndexError):
        return None


# ── Telegram handlers ────────────────────────────────────────────────────

@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! Just chat with me naturally:\n\n"
        "\"add fix login for trewit, urgent\"\n"
        "\"done with the invoice\"\n"
        "\"what's on my list?\"\n"
        "\"urgent stuff\"\n"
        "\"daily\"\n"
        "\"board\"\n\n"
        "Slash commands work too: /add /done /list /urgent /daily /board"
    )


@auth
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /add <task description>")
        return
    # Let AI parse it for client/due/urgent extraction
    result = parse_with_ai(f"add task: {text}")
    if result and result.get("action") == "add":
        msg = action_add(
            result.get("description", text),
            client=result.get("client"),
            due=result.get("due"),
            urgent=result.get("urgent", False),
            effort=result.get("effort"),
        )
    else:
        msg = action_add(text)
    await update.message.reply_text(msg)


@auth
async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search = " ".join(context.args) if context.args else ""
    if not search:
        await update.message.reply_text("Usage: /done <search term>")
        return
    await update.message.reply_text(action_done(search))


@auth
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(action_list(), parse_mode="Markdown")


@auth
async def cmd_urgent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(action_list(urgent_only=True))


@auth
async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating...")
    await update.message.reply_text(action_daily())


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
async def natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse any message with AI and execute the right action."""
    text = update.message.text.strip()
    if not text:
        return

    result = parse_with_ai(text)

    if not result:
        # AI unavailable, fall back to adding to inbox
        msg = action_add(text)
        await update.message.reply_text(msg)
        return

    action = result.get("action", "unknown")

    if action == "add":
        msg = action_add(
            result.get("description", text),
            client=result.get("client"),
            due=result.get("due"),
            urgent=result.get("urgent", False),
            effort=result.get("effort"),
        )
        await update.message.reply_text(msg)

    elif action == "done":
        msg = action_done(result.get("search", text))
        await update.message.reply_text(msg)

    elif action == "list":
        msg = action_list(urgent_only=result.get("urgent_only", False))
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif action == "daily":
        await update.message.reply_text("Generating...")
        await update.message.reply_text(action_daily())

    elif action == "board":
        refresh_board()
        board_path = TASKS_DIR / "board.html"
        if board_path.exists():
            await update.message.reply_document(
                document=open(board_path, "rb"),
                filename="board.html",
                caption="Open in your browser",
            )

    elif action == "unknown":
        reply = result.get("reply", "Didn't catch that — try something like 'add fix bug for trewit' or 'show my list'")
        await update.message.reply_text(reply)


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()

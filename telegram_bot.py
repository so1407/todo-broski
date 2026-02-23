#!/usr/bin/env python3
"""Telegram bot + local web server for task management.

Chat naturally via Telegram:
  "add fix login bug for trewit, urgent"
  "done with the invoice"
  "what's on my list?"

Web board at http://localhost:8347 with inline task completion.
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
from aiohttp import web
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
WEB_PORT = 8347


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


# ── Core actions ─────────────────────────────────────────────────────────

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


def action_done_exact(source_file: str, line_number: int) -> str:
    """Complete a task by exact file + line number (used by web board)."""
    filepath = Path(source_file)
    if not filepath.exists():
        return "File not found."
    complete_task(filepath, line_number)
    refresh_board()
    return "Done"


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


def action_week() -> str:
    from datetime import timedelta
    tasks = read_all_tasks()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    done_this_week = [
        t for t in tasks
        if t.done and t.done_date and t.done_date >= week_start
    ]
    still_open = [t for t in tasks if not t.done]
    urgent_open = [t for t in still_open if t.urgent or t.is_overdue]

    lines = [f"📊 *Week of {week_start.isoformat()}*\n"]

    if done_this_week:
        lines.append(f"✅ *{len(done_this_week)} completed*\n")
        grouped: dict[str, list] = {}
        for t in done_this_week:
            name = Path(t.source_file).stem.replace("-", " ").title()
            grouped.setdefault(name, []).append(t)
        for project, group in sorted(grouped.items()):
            lines.append(f"*{project}:*")
            for t in group:
                lines.append(f"  ✓ {t.description}")
            lines.append("")
    else:
        lines.append("No tasks completed yet this week.\n")

    lines.append(f"📋 {len(still_open)} still open ({len(urgent_open)} urgent)")

    return "\n".join(lines)


def action_daily() -> str:
    from ai import generate_daily
    hours = config.get("daily", {}).get("available_hours", 6)
    content = generate_daily(TASKS_DIR, available_hours=hours)
    daily_file = TASKS_DIR / "daily" / f"{date.today().isoformat()}.md"
    daily_file.write_text(content)
    return content


# ── Natural language parser ──────────────────────────────────────────────

def parse_with_ai(text: str) -> dict | None:
    client = get_ai_client()
    if not client:
        return None

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

Weekly review (what was done this week):
{{"action": "week"}}

If the message is conversational or unclear:
{{"action": "unknown", "reply": "your friendly response asking for clarification"}}

Match client names fuzzily to known projects. If someone says "trewit" match to "Trewit", "pmu" to "Pmu" etc.
For "done" actions, extract the most distinctive keyword from what they describe to use as search term.""",
    )

    try:
        result_text = response.content[0].text.strip()
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
        f"Web board: http://localhost:{WEB_PORT}"
    )


@auth
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /add <task description>")
        return
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
async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(action_week(), parse_mode="Markdown")


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
    text = update.message.text.strip()
    if not text:
        return

    result = parse_with_ai(text)

    if not result:
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
    elif action == "week":
        await update.message.reply_text(action_week(), parse_mode="Markdown")
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
        reply = result.get("reply", "Didn't catch that — try 'add fix bug for trewit' or 'show my list'")
        await update.message.reply_text(reply)


# ── Web server (serves board + API for done/add) ────────────────────────

async def web_board(request):
    """Serve the board HTML."""
    refresh_board()
    board_path = TASKS_DIR / "board.html"
    if board_path.exists():
        return web.FileResponse(board_path)
    return web.Response(text="No board yet. Add some tasks first.")


async def web_done(request):
    """API: mark a task done by source_file + line_number."""
    try:
        data = await request.json()
        source = data.get("source_file", "")
        line = int(data.get("line_number", 0))
        result = action_done_exact(source, line)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def web_add(request):
    """API: add a task."""
    try:
        data = await request.json()
        result = action_add(
            data.get("description", ""),
            client=data.get("client"),
            due=data.get("due"),
            urgent=data.get("urgent", False),
            effort=data.get("effort"),
        )
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", web_board)
    app.router.add_post("/api/done", web_done)
    app.router.add_post("/api/add", web_add)
    return app


# ── Main: run both Telegram bot and web server ──────────────────────────

async def run_all():
    ensure_structure()
    token = config.get("telegram", {}).get("token")
    if not token:
        print("Error: No telegram token in ~/.tasks/config.yaml")
        sys.exit(1)

    # Set up Telegram bot
    tg_app = Application.builder().token(token).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("help", cmd_start))
    tg_app.add_handler(CommandHandler("add", cmd_add))
    tg_app.add_handler(CommandHandler("done", cmd_done))
    tg_app.add_handler(CommandHandler("list", cmd_list))
    tg_app.add_handler(CommandHandler("urgent", cmd_urgent))
    tg_app.add_handler(CommandHandler("daily", cmd_daily))
    tg_app.add_handler(CommandHandler("week", cmd_week))
    tg_app.add_handler(CommandHandler("board", cmd_board))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language))

    # Set up web server
    web_app = create_web_app()
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)

    # Start both
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling()
    await site.start()

    logger.info(f"Bot + web server running on http://localhost:{WEB_PORT}")

    # Keep running
    try:
        await asyncio.Event().wait()
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await runner.cleanup()


def main():
    asyncio.run(run_all())


if __name__ == "__main__":
    main()

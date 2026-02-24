#!/usr/bin/env python3
"""ToDo Schwesti — Telegram bot backed by Supabase.

Chat naturally:
  "add fix login bug for trewit, urgent"
  "done with the invoice"
  "what's on my list?"

Deploy to Railway for 24/7 operation.
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
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).parent))

from packages.core.config import get_config, get_anthropic_key, get_vercel_url
from packages.core.db import DB
from packages.core.models import Task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = get_config()
ALLOWED_CHAT_ID = config.get("telegram", {}).get("chat_id")
AI_MODEL = "claude-haiku-4-5-20251001"


def get_ai_client():
    try:
        return anthropic.Anthropic(api_key=get_anthropic_key())
    except SystemExit:
        return None


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
    slug = None
    if client:
        slug = re.sub(r"[^a-z0-9]+", "-", client.lower()).strip("-")

    task = DB.add_task(
        description=description,
        project_slug=slug,
        due=due,
        urgent=urgent,
        effort=effort,
        source="telegram",
    )
    return f"Added to {task.project_name}: {description}"


def action_done(search: str) -> str:
    return DB.complete_task_by_search(search)


def action_list(urgent_only: bool = False) -> str:
    if urgent_only:
        tasks = DB.list_tasks(done=False, urgent_only=True)
    else:
        tasks = DB.list_tasks(done=False)

    if not tasks:
        return "No urgent tasks!" if urgent_only else "No open tasks!"

    grouped: dict[str, list[Task]] = {}
    for t in tasks:
        grouped.setdefault(t.project_name, []).append(t)

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
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    done_this_week = DB.get_tasks_completed_since(week_start)
    still_open = DB.list_tasks(done=False)
    urgent_open = [t for t in still_open if t.urgent or t.is_overdue]

    lines = [f"📊 *Week of {week_start.isoformat()}*\n"]

    if done_this_week:
        lines.append(f"✅ *{len(done_this_week)} completed*\n")
        grouped: dict[str, list] = {}
        for t in done_this_week:
            grouped.setdefault(t.project_name, []).append(t)
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
    content = generate_daily(available_hours=hours)
    DB.save_daily_plan(date.today(), content)
    return content


# ── Natural language parser ──────────────────────────────────────────────

def parse_with_ai(text: str) -> dict | None:
    client = get_ai_client()
    if not client:
        return None

    projects = DB.list_projects()
    project_names = [p.name for p in projects if p.slug != "inbox"]

    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": text}],
        system=f"""You are a task bot parser. The user sends casual messages. Parse them into JSON actions.

Known projects: {', '.join(project_names) if project_names else 'none yet'}
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
    board_url = get_vercel_url()
    board_line = f"\n\nBoard: {board_url}" if board_url else ""
    await update.message.reply_text(
        "Hey! Just chat with me naturally:\n\n"
        "\"add fix login for trewit, urgent\"\n"
        "\"done with the invoice\"\n"
        "\"what's on my list?\"\n"
        "\"urgent stuff\"\n"
        "\"daily\"\n"
        "\"board\""
        f"{board_line}"
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
    board_url = get_vercel_url()
    if board_url:
        await update.message.reply_text(f"📋 Board: {board_url}")
    else:
        await update.message.reply_text("No board URL configured.")


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
        board_url = get_vercel_url()
        if board_url:
            await update.message.reply_text(f"📋 Board: {board_url}")
        else:
            await update.message.reply_text("No board URL configured.")
    elif action == "unknown":
        reply = result.get("reply", "Didn't catch that — try 'add fix bug for trewit' or 'show my list'")
        await update.message.reply_text(reply)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_TOKEN") or config.get("telegram", {}).get("token")
    if not token:
        print("Error: No telegram token. Set TELEGRAM_TOKEN env var or add telegram.token to ~/.tasks/config.yaml")
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("urgent", cmd_urgent))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("board", cmd_board))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language))

    logger.info("ToDo Schwesti bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()

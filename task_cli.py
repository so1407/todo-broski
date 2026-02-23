#!/usr/bin/env python3
"""Personal task management CLI."""

import webbrowser
from datetime import date
from pathlib import Path

import click

from parser import (
    TASKS_DIR,
    add_task_to_file,
    client_to_filename,
    complete_task,
    ensure_structure,
    load_config,
    parse_date,
    read_all_tasks,
    read_tasks,
    task_to_line,
    Task,
)
from board import generate_board


def refresh_board():
    try:
        generate_board(TASKS_DIR)
    except Exception:
        pass


@click.group()
def cli():
    """Personal task manager."""
    ensure_structure()


# ── add ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("description")
@click.option("--client", "-c", default=None, help="Client/project name")
@click.option("--due", "-d", default=None, help="Due date (YYYY-MM-DD, today, tomorrow, mon-sun)")
@click.option("--urgent", "-u", is_flag=True, help="Mark as urgent")
@click.option("--effort", "-e", default=None, help="Effort estimate (e.g. 2h, 30m)")
def add(description, client, due, urgent, effort):
    """Add a new task."""
    task = Task(
        description=description,
        done=False,
        due=parse_date(due) if due else None,
        urgent=urgent,
        effort=effort,
    )
    line = task_to_line(task)

    if client:
        filename = client_to_filename(client)
        filepath = TASKS_DIR / filename
    else:
        filepath = TASKS_DIR / "inbox.md"

    add_task_to_file(filepath, line)
    refresh_board()
    target = filepath.stem.replace("-", " ").title()
    click.echo(f"  Added to {target}: {description}")


# ── list ─────────────────────────────────────────────────────────────────

@cli.command("list")
@click.option("--client", "-c", default=None, help="Filter by client/project")
@click.option("--urgent", "-u", is_flag=True, help="Show only urgent tasks")
@click.option("--due-soon", "-d", is_flag=True, help="Show only tasks due within 3 days")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include completed tasks")
def list_tasks(client, urgent, due_soon, show_all):
    """List tasks across all projects."""
    tasks = read_all_tasks()

    if client:
        slug = client_to_filename(client)
        tasks = [t for t in tasks if Path(t.source_file).name == slug]

    if not show_all:
        tasks = [t for t in tasks if not t.done]

    if urgent:
        tasks = [t for t in tasks if t.urgent]

    if due_soon:
        tasks = [t for t in tasks if t.is_due_soon or t.is_overdue]

    if not tasks:
        click.echo("  No tasks found.")
        return

    # Group by source file
    grouped: dict[str, list[Task]] = {}
    for t in tasks:
        grouped.setdefault(t.source_file, []).append(t)

    for source, group in grouped.items():
        heading = Path(source).stem.replace("-", " ").title()
        click.echo(f"\n  {click.style(heading, bold=True)}")

        for t in group:
            color = "white"
            prefix = ""
            if t.is_overdue:
                color = "red"
                prefix = "OVERDUE "
            elif t.urgent:
                color = "yellow"
                prefix = ""
            elif t.is_due_soon:
                color = "cyan"

            due_str = f" (due {t.due})" if t.due else ""
            effort_str = f" [{t.effort}]" if t.effort else ""
            urgent_str = " *urgent*" if t.urgent else ""
            checkbox = "[x]" if t.done else "[ ]"

            line = f"    {checkbox} {prefix}{t.description}{due_str}{effort_str}{urgent_str}"
            click.echo(click.style(line, fg=color))

    click.echo()


# ── done ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("search")
def done(search):
    """Mark a task as complete (fuzzy search by description)."""
    tasks = read_all_tasks()
    open_tasks = [t for t in tasks if not t.done]

    # Fuzzy match
    search_lower = search.lower()
    matches = [t for t in open_tasks if search_lower in t.description.lower()]

    if not matches:
        click.echo(f"  No open tasks matching '{search}'.")
        return

    if len(matches) == 1:
        target = matches[0]
    else:
        click.echo(f"  Multiple matches for '{search}':\n")
        for i, t in enumerate(matches, 1):
            project = Path(t.source_file).stem.replace("-", " ").title()
            click.echo(f"    {i}. {t.description} ({project})")
        click.echo()
        choice = click.prompt("  Pick one", type=int)
        if choice < 1 or choice > len(matches):
            click.echo("  Invalid choice.")
            return
        target = matches[choice - 1]

    complete_task(Path(target.source_file), target.line_number)
    refresh_board()
    click.echo(f"  Done: {target.description}")


# ── inbox ────────────────────────────────────────────────────────────────

@cli.command()
def inbox():
    """Show unsorted inbox tasks."""
    tasks = read_tasks(TASKS_DIR / "inbox.md")
    open_tasks = [t for t in tasks if not t.done]

    if not open_tasks:
        click.echo("  Inbox is empty.")
        return

    click.echo(f"\n  {click.style('Inbox', bold=True)} ({len(open_tasks)} tasks)\n")
    for t in open_tasks:
        due_str = f" (due {t.due})" if t.due else ""
        effort_str = f" [{t.effort}]" if t.effort else ""
        urgent_str = " *urgent*" if t.urgent else ""
        click.echo(f"    [ ] {t.description}{due_str}{effort_str}{urgent_str}")
    click.echo()


# ── board ────────────────────────────────────────────────────────────────

@cli.command()
def board():
    """Generate and open the HTML kanban board."""
    from board import generate_board

    path = generate_board(TASKS_DIR)
    click.echo(f"  Board generated: {path}")
    webbrowser.open(f"file://{path}")


# ── daily ────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--send", is_flag=True, help="Also send the daily list via email")
def daily(send):
    """Generate tomorrow's task list using AI."""
    from ai import generate_daily

    config = load_config()
    hours = config.get("daily", {}).get("available_hours", 6)

    click.echo("  Generating daily list...")
    content = generate_daily(TASKS_DIR, available_hours=hours)

    # Save to daily file
    tomorrow = date.today()
    daily_file = TASKS_DIR / "daily" / f"{tomorrow.isoformat()}.md"
    daily_file.write_text(content)

    click.echo(f"\n{content}")
    click.echo(f"\n  Saved to {daily_file}")

    if send:
        _send_telegram(content, config)


# ── sort ─────────────────────────────────────────────────────────────────

@cli.command()
def sort():
    """AI sorts inbox tasks into the correct project files."""
    from ai import sort_inbox

    results = sort_inbox(TASKS_DIR)
    if not results:
        click.echo("  Nothing to sort (inbox empty or all tasks already sorted).")
        return

    for desc, target in results:
        target_name = Path(target).stem.replace("-", " ").title()
        click.echo(f"  {desc} -> {target_name}")


# ── telegram helper ──────────────────────────────────────────────────────

def _send_telegram(content: str, config: dict):
    """Send the daily list via Telegram."""
    import requests

    tg = config.get("telegram", {})
    token = tg.get("token")
    chat_id = tg.get("chat_id")

    if not token or not chat_id:
        click.echo("  Telegram not configured. Edit ~/.tasks/config.yaml")
        return

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": content},
        )
        if r.ok:
            click.echo("  Sent via Telegram!")
        else:
            click.echo(f"  Telegram failed: {r.text}")
    except Exception as e:
        click.echo(f"  Telegram failed: {e}")


if __name__ == "__main__":
    cli()

#!/usr/bin/env python3
"""ToDo Schwesti — personal task management CLI backed by Supabase."""

import webbrowser
from datetime import date, timedelta
from pathlib import Path

import click

from packages.core.config import get_config, get_vercel_url, TASKS_DIR
from packages.core.db import DB
from packages.core.markdown import parse_date, task_to_line, export_project_to_markdown
from packages.core.models import Task


@click.group()
def cli():
    """ToDo Schwesti — personal task manager."""
    pass


# ── add ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("description")
@click.option("--client", "-c", default=None, help="Client/project name")
@click.option("--due", "-d", default=None, help="Due date (YYYY-MM-DD, today, tomorrow, mon-sun)")
@click.option("--urgent", "-u", is_flag=True, help="Mark as urgent")
@click.option("--effort", "-e", default=None, help="Effort estimate (e.g. 2h, 30m)")
def add(description, client, due, urgent, effort):
    """Add a new task."""
    slug = None
    if client:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", client.lower()).strip("-")

    task = DB.add_task(
        description=description,
        project_slug=slug,
        due=due,
        urgent=urgent,
        effort=effort,
        source="cli",
    )
    click.echo(f"  Added to {task.project_name}: {description}")


# ── list ─────────────────────────────────────────────────────────────────

@cli.command("list")
@click.option("--client", "-c", default=None, help="Filter by client/project")
@click.option("--urgent", "-u", is_flag=True, help="Show only urgent tasks")
@click.option("--due-soon", "-d", is_flag=True, help="Show only tasks due within 3 days")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include completed tasks")
def list_tasks(client, urgent, due_soon, show_all):
    """List tasks across all projects."""
    import re

    slug = None
    if client:
        slug = re.sub(r"[^a-z0-9]+", "-", client.lower()).strip("-")

    if show_all:
        tasks = DB.list_tasks(project_slug=slug)
    else:
        tasks = DB.list_tasks(project_slug=slug, done=False)

    if urgent:
        tasks = [t for t in tasks if t.urgent or t.is_overdue]

    if due_soon:
        tasks = [t for t in tasks if t.is_due_soon or t.is_overdue]

    if not tasks:
        click.echo("  No tasks found.")
        return

    # Group by project
    grouped: dict[str, list[Task]] = {}
    for t in tasks:
        grouped.setdefault(t.project_name or "Unknown", []).append(t)

    for project, group in grouped.items():
        click.echo(f"\n  {click.style(project, bold=True)}")

        for t in group:
            color = "white"
            prefix = ""
            if t.is_overdue:
                color = "red"
                prefix = "OVERDUE "
            elif t.urgent:
                color = "yellow"
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
    tasks = DB.list_tasks(done=False)
    search_lower = search.lower()
    matches = [t for t in tasks if search_lower in t.description.lower()]

    if not matches:
        click.echo(f"  No open tasks matching '{search}'.")
        return

    if len(matches) == 1:
        target = matches[0]
    else:
        click.echo(f"  Multiple matches for '{search}':\n")
        for i, t in enumerate(matches, 1):
            click.echo(f"    {i}. {t.description} ({t.project_name})")
        click.echo()
        choice = click.prompt("  Pick one", type=int)
        if choice < 1 or choice > len(matches):
            click.echo("  Invalid choice.")
            return
        target = matches[choice - 1]

    DB.complete_task_by_id(target.id)
    click.echo(f"  Done: {target.description}")


# ── inbox ────────────────────────────────────────────────────────────────

@cli.command()
def inbox():
    """Show unsorted inbox tasks."""
    tasks = DB.list_tasks(project_slug="inbox", done=False)

    if not tasks:
        click.echo("  Inbox is empty.")
        return

    click.echo(f"\n  {click.style('Inbox', bold=True)} ({len(tasks)} tasks)\n")
    for t in tasks:
        due_str = f" (due {t.due})" if t.due else ""
        effort_str = f" [{t.effort}]" if t.effort else ""
        urgent_str = " *urgent*" if t.urgent else ""
        click.echo(f"    [ ] {t.description}{due_str}{effort_str}{urgent_str}")
    click.echo()


# ── board ────────────────────────────────────────────────────────────────

@cli.command()
def board():
    """Open the web kanban board."""
    url = get_vercel_url()
    if url:
        click.echo(f"  Opening board: {url}")
        webbrowser.open(url)
    else:
        click.echo("  No board URL configured. Set vercel_url in ~/.tasks/config.yaml")


# ── daily ────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--send", is_flag=True, help="Also send the daily list via Telegram")
def daily(send):
    """Generate today's task list using AI."""
    from ai import generate_daily

    config = get_config()
    hours = config.get("daily", {}).get("available_hours", 6)

    click.echo("  Generating daily list...")
    content = generate_daily(available_hours=hours)

    # Save to Supabase
    today = date.today()
    DB.save_daily_plan(today, content)

    # Also save local backup
    daily_dir = TASKS_DIR / "daily"
    daily_dir.mkdir(exist_ok=True)
    daily_file = daily_dir / f"{today.isoformat()}.md"
    daily_file.write_text(content)

    click.echo(f"\n{content}")
    click.echo(f"\n  Saved to Supabase + {daily_file}")

    if send:
        _send_telegram(content, config)


# ── week ─────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--send", is_flag=True, help="Also send via Telegram")
def week(send):
    """Show weekly report: what you got done + what's still open."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    done_this_week = DB.get_tasks_completed_since(week_start)
    still_open = DB.list_tasks(done=False)
    urgent_open = [t for t in still_open if t.urgent or t.is_overdue]

    lines = [f"  {click.style(f'Week of {week_start.isoformat()}', bold=True)}\n"]

    if done_this_week:
        lines.append(f"  {click.style(f'{len(done_this_week)} completed', fg='green')}\n")
        grouped: dict[str, list] = {}
        for t in done_this_week:
            grouped.setdefault(t.project_name, []).append(t)
        for project, group in sorted(grouped.items()):
            lines.append(f"    {project}:")
            for t in group:
                lines.append(f"      [x] {t.description}")
    else:
        lines.append("  No tasks completed yet this week.")

    lines.append(f"\n  {len(still_open)} still open ({len(urgent_open)} urgent)")

    report = "\n".join(lines)
    click.echo(f"\n{report}\n")

    if send:
        tg_lines = [f"Week of {week_start.isoformat()}\n"]
        if done_this_week:
            tg_lines.append(f"{len(done_this_week)} completed:\n")
            grouped2: dict[str, list] = {}
            for t in done_this_week:
                grouped2.setdefault(t.project_name, []).append(t)
            for project, group in sorted(grouped2.items()):
                tg_lines.append(f"\n{project}:")
                for t in group:
                    tg_lines.append(f"  [x] {t.description}")
        tg_lines.append(f"\n{len(still_open)} still open ({len(urgent_open)} urgent)")
        config = get_config()
        _send_telegram("\n".join(tg_lines), config)


# ── sort ─────────────────────────────────────────────────────────────────

@cli.command()
def sort():
    """AI sorts inbox tasks into the correct project files."""
    from ai import sort_inbox

    results = sort_inbox()
    if not results:
        click.echo("  Nothing to sort (inbox empty or all tasks already sorted).")
        return

    for desc, target in results:
        click.echo(f"  {desc} -> {target}")


# ── export ───────────────────────────────────────────────────────────────

@cli.command()
@click.option("--output", "-o", default=None, help="Output directory (default: ~/.tasks/)")
def export(output):
    """Export all Supabase tasks back to markdown files."""
    out_dir = Path(output) if output else TASKS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    projects = DB.list_projects()
    tasks = DB.list_tasks()

    # Group tasks by project
    by_project: dict[str, list[Task]] = {}
    project_names: dict[str, str] = {}
    for p in projects:
        project_names[p.slug] = p.name
        by_project[p.slug] = []
    for t in tasks:
        by_project.setdefault(t.project_slug, []).append(t)

    exported = 0
    for slug, group in by_project.items():
        if not group and slug not in project_names:
            continue
        name = project_names.get(slug, slug.replace("-", " ").title())
        md = export_project_to_markdown(name, group)
        filepath = out_dir / f"{slug}.md"
        filepath.write_text(md)
        active = sum(1 for t in group if not t.done)
        click.echo(f"  {name} -> {filepath.name} ({active} active)")
        exported += 1

    click.echo(f"\n  Exported {exported} projects to {out_dir}")


# ── telegram helper ──────────────────────────────────────────────────────

def _send_telegram(content: str, config: dict):
    """Send a message via Telegram."""
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

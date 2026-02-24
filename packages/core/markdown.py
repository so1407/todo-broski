"""Markdown parsing and export — extracted from the original parser.py."""

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Task

TASK_RE = re.compile(r"^- \[([ xX])\] (.+)$")
TAG_RE = re.compile(r"@(\w+)(?:\(([^)]*)\))?", re.IGNORECASE)
HEADING1_RE = re.compile(r"^# (.+)$")


def parse_date(s: str) -> date | None:
    """Parse a date string, accepting YYYY-MM-DD or relative words."""
    s = s.strip().lower()
    today = date.today()

    if s in ("today", "tod"):
        return today
    if s in ("tomorrow", "tom"):
        return today + timedelta(days=1)

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    short_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    for i, (full, short) in enumerate(zip(days, short_days)):
        if s in (full, short):
            current_day = today.weekday()
            delta = (i - current_day) % 7
            if delta == 0:
                delta = 7
            return today + timedelta(days=delta)

    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_task_line(line: str) -> Task | None:
    """Parse a single markdown task line into a Task object."""
    m = TASK_RE.match(line.rstrip())
    if not m:
        return None

    done = m.group(1).lower() == "x"
    full_text = m.group(2)

    tags = {}
    for tag_match in TAG_RE.finditer(full_text):
        tag_name = tag_match.group(1).lower()
        tag_value = tag_match.group(2)
        tags[tag_name] = tag_value

    description = TAG_RE.sub("", full_text).strip()

    return Task(
        description=description,
        done=done,
        due=parse_date(tags["due"]) if "due" in tags else None,
        urgent="urgent" in tags,
        effort=tags.get("effort"),
        done_date=parse_date(tags["done"]) if "done" in tags else None,
        raw_line=line.rstrip(),
    )


def task_to_line(task: Task) -> str:
    """Serialize a Task back to a markdown line."""
    checkbox = "[x]" if task.done else "[ ]"
    parts = [f"- {checkbox} {task.description}"]
    if task.due:
        parts.append(f"@due({task.due.isoformat()})")
    if task.urgent:
        parts.append("@urgent")
    if task.effort:
        parts.append(f"@effort({task.effort})")
    if task.done and task.done_date:
        parts.append(f"@done({task.done_date.isoformat()})")
    return " ".join(parts)


def get_project_heading(filepath: Path) -> str:
    """Read the # heading from a project file, or derive from filename."""
    try:
        with open(filepath) as f:
            for line in f:
                m = HEADING1_RE.match(line.strip())
                if m:
                    return m.group(1)
    except FileNotFoundError:
        pass
    return filepath.stem.replace("-", " ").title()


def read_tasks_from_file(filepath: Path) -> list[Task]:
    """Read all tasks from one .md file (for migration)."""
    tasks = []
    heading = get_project_heading(filepath)
    slug = filepath.stem

    try:
        with open(filepath) as f:
            for i, line in enumerate(f, 1):
                task = parse_task_line(line)
                if task:
                    task.source_file = str(filepath)
                    task.line_number = i
                    task.project_name = heading
                    task.project_slug = slug
                    tasks.append(task)
    except FileNotFoundError:
        pass
    return tasks


def export_project_to_markdown(project_name: str, tasks: list[Task]) -> str:
    """Export a project's tasks back to markdown format."""
    lines = [f"# {project_name}", "", "## Active"]
    active = [t for t in tasks if not t.done]
    done = [t for t in tasks if t.done]

    for t in active:
        lines.append(task_to_line(t))

    lines.append("")
    lines.append("## Done")
    for t in done:
        lines.append(task_to_line(t))

    return "\n".join(lines) + "\n"

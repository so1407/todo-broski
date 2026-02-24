"""ToDo Schwesti: Claude AI integration for daily list generation and inbox sorting."""

import re
from datetime import date

import anthropic

from packages.core.config import get_anthropic_key
from packages.core.db import DB
from packages.core.models import Task

MODEL = "claude-sonnet-4-20250514"


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_anthropic_key())


def generate_daily(available_hours: int = 6) -> str:
    """Generate a daily task list using Claude. Returns markdown string."""
    tasks = DB.list_tasks(done=False)

    if not tasks:
        return "# Daily Tasks\n\nNo open tasks. Enjoy your day!"

    today = date.today()
    weekday = today.strftime("%A")

    by_project: dict[str, list[Task]] = {}
    for t in tasks:
        by_project.setdefault(t.project_name, []).append(t)

    task_text = ""
    for project, group in sorted(by_project.items()):
        task_text += f"\n### {project}\n"
        for t in group:
            parts = [f"- {t.description}"]
            if t.due:
                days_until = (t.due - today).days
                if days_until < 0:
                    parts.append(f"**OVERDUE by {abs(days_until)} days** (due {t.due})")
                elif days_until == 0:
                    parts.append(f"**DUE TODAY** ({t.due})")
                else:
                    parts.append(f"due {t.due} ({days_until} days)")
            if t.urgent:
                parts.append("**URGENT**")
            if t.effort:
                parts.append(f"effort: {t.effort}")
            task_text += "  ".join(parts) + "\n"

    prompt = f"""You are a personal task scheduler. Given the open tasks below, pick a realistic day's work (about {available_hours} hours).

Rules:
- Overdue tasks MUST be included unless physically impossible to fit
- Tasks due today MUST be included
- Urgent tasks get priority over non-urgent
- Leave ~20% buffer for interruptions
- Group the output by project
- Be realistic about what fits — better to finish fewer tasks than to overcommit
- Output a clean markdown list, nothing else. Start with "# Tasks for {today.isoformat()}" heading.
- Under each project heading, list the selected tasks as checkboxes (- [ ])
- At the bottom, add a brief "---" separator and a one-line summary of total estimated effort

Today: {today.isoformat()} ({weekday})
Available time: {available_hours} hours

Open tasks:
{task_text}"""

    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


def sort_inbox() -> list[tuple[str, str]]:
    """Sort inbox tasks into project files using Claude. Returns [(description, target_project), ...]."""
    inbox_tasks = DB.list_tasks(project_slug="inbox", done=False)

    if not inbox_tasks:
        return []

    projects = DB.list_projects()
    project_names = [p.name for p in projects if p.slug != "inbox"]

    if not project_names:
        project_list = "(no existing projects — suggest new project names)"
    else:
        project_list = "\n".join(f"- {p}" for p in project_names)

    task_list = ""
    for i, t in enumerate(inbox_tasks):
        parts = [t.description]
        if t.due:
            parts.append(f"due {t.due}")
        if t.urgent:
            parts.append("urgent")
        if t.effort:
            parts.append(f"effort: {t.effort}")
        task_list += f"{i+1}. {' | '.join(parts)}\n"

    prompt = f"""You are sorting tasks into project files. For each inbox task, decide which project it belongs to.

Existing projects:
{project_list}

Inbox tasks:
{task_list}

For each task, respond with EXACTLY one line in this format:
NUMBER -> Project Name

If a task doesn't fit any existing project, use:
NUMBER -> NEW: Suggested Project Name

Example:
1 -> Acme Corp
2 -> NEW: Marketing
3 -> Personal

Respond with ONLY the mapping lines, nothing else."""

    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    results = []
    lines = response.content[0].text.strip().split("\n")

    # Build project slug lookup
    slug_map = {p.name.lower(): p.slug for p in projects}

    for line in lines:
        line = line.strip()
        if "->" not in line:
            continue
        parts = line.split("->", 1)
        try:
            idx = int(parts[0].strip()) - 1
        except ValueError:
            continue
        target_name = parts[1].strip()

        if idx < 0 or idx >= len(inbox_tasks):
            continue

        if target_name.upper().startswith("NEW:"):
            target_name = target_name[4:].strip()

        task = inbox_tasks[idx]
        target_slug = slug_map.get(target_name.lower())
        if not target_slug:
            target_slug = re.sub(r"[^a-z0-9]+", "-", target_name.lower()).strip("-")

        # Move the task to the target project
        DB.move_task(task.id, target_slug)
        results.append((task.description, target_name))

    return results

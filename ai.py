"""Claude API integration for daily list generation and inbox sorting."""

import os
from datetime import date
from pathlib import Path

import anthropic

from parser import (
    TASKS_DIR,
    add_task_to_file,
    client_to_filename,
    load_config,
    read_all_tasks,
    read_tasks,
    remove_task,
)

MODEL = "claude-sonnet-4-20250514"


def _get_client() -> anthropic.Anthropic:
    """Create an Anthropic client using config or env var."""
    config = load_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY") or config.get("anthropic_api_key")
    if not api_key:
        raise SystemExit(
            "Error: No API key found. Set ANTHROPIC_API_KEY env var or add anthropic_api_key to ~/.tasks/config.yaml"
        )
    return anthropic.Anthropic(api_key=api_key)


def generate_daily(tasks_dir: Path = TASKS_DIR, available_hours: int = 6) -> str:
    """Generate a daily task list using Claude. Returns markdown string."""
    tasks = read_all_tasks(tasks_dir)
    open_tasks = [t for t in tasks if not t.done]

    if not open_tasks:
        return "# Daily Tasks\n\nNo open tasks. Enjoy your day!"

    today = date.today()
    weekday = today.strftime("%A")

    # Format tasks for the prompt
    by_project: dict[str, list] = {}
    for t in open_tasks:
        project = Path(t.source_file).stem.replace("-", " ").title()
        by_project.setdefault(project, []).append(t)

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


def sort_inbox(tasks_dir: Path = TASKS_DIR) -> list[tuple[str, str]]:
    """Sort inbox tasks into project files using Claude. Returns [(description, target_file), ...]."""
    inbox_path = tasks_dir / "inbox.md"
    inbox_tasks = read_tasks(inbox_path)
    open_inbox = [t for t in inbox_tasks if not t.done]

    if not open_inbox:
        return []

    # Get existing project files
    project_files = [f.stem.replace("-", " ").title()
                     for f in sorted(tasks_dir.glob("*.md"))
                     if f.name != "inbox.md"]

    if not project_files:
        # No projects yet — ask Claude to suggest project names
        project_list = "(no existing projects — suggest new project names)"
    else:
        project_list = "\n".join(f"- {p}" for p in project_files)

    task_list = ""
    for i, t in enumerate(open_inbox):
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

    # Parse response and move tasks
    results = []
    lines = response.content[0].text.strip().split("\n")

    # Process in reverse order so line numbers stay valid
    moves = []
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

        if idx < 0 or idx >= len(open_inbox):
            continue

        # Handle NEW: prefix
        if target_name.upper().startswith("NEW:"):
            target_name = target_name[4:].strip()

        task = open_inbox[idx]
        filename = client_to_filename(target_name)
        moves.append((task, filename, target_name))

    # Sort moves by line number descending to preserve indices during removal
    moves.sort(key=lambda x: x[0].line_number, reverse=True)

    for task, filename, display_name in moves:
        # Remove from inbox
        removed = remove_task(inbox_path, task.line_number)
        if removed:
            # Add to target project file
            from parser import task_to_line
            target_path = tasks_dir / filename
            add_task_to_file(target_path, task_to_line(task))
            results.append((task.description, filename))

    results.reverse()  # Back to original order for display
    return results

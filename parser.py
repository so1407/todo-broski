"""Core data layer: Task dataclass, markdown parsing, file read/write."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

TASKS_DIR = Path.home() / ".tasks"
TASK_RE = re.compile(r"^- \[([ xX])\] (.+)$")
TAG_RE = re.compile(r"@(\w+)(?:\(([^)]*)\))?", re.IGNORECASE)
HEADING1_RE = re.compile(r"^# (.+)$")


@dataclass
class Task:
    description: str
    done: bool
    due: date | None = None
    urgent: bool = False
    effort: str | None = None
    done_date: date | None = None
    source_file: str = ""
    line_number: int = 0
    raw_line: str = ""

    @property
    def project_name(self) -> str:
        """Derive display name from source file (e.g. 'acme-corp.md' -> 'Acme Corp')."""
        if not self.source_file:
            return "Unknown"
        stem = Path(self.source_file).stem
        return stem.replace("-", " ").title()

    @property
    def is_overdue(self) -> bool:
        return self.due is not None and not self.done and self.due < date.today()

    @property
    def is_due_soon(self) -> bool:
        if self.due is None or self.done:
            return False
        days = (self.due - date.today()).days
        return 0 <= days <= 3


def parse_date(s: str) -> date | None:
    """Parse a date string, accepting YYYY-MM-DD or relative words."""
    s = s.strip().lower()
    today = date.today()

    # Relative dates
    if s in ("today", "tod"):
        return today
    if s in ("tomorrow", "tom"):
        from datetime import timedelta
        return today + timedelta(days=1)

    # Day names (next occurrence)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    short_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    for i, (full, short) in enumerate(zip(days, short_days)):
        if s in (full, short):
            from datetime import timedelta
            current_day = today.weekday()
            delta = (i - current_day) % 7
            if delta == 0:
                delta = 7  # next week if today
            return today + timedelta(days=delta)

    # ISO format
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_task_line(line: str, source: str = "", lineno: int = 0) -> Task | None:
    """Parse a single markdown line into a Task, or None if not a task line."""
    m = TASK_RE.match(line.rstrip())
    if not m:
        return None

    done = m.group(1).lower() == "x"
    full_text = m.group(2)

    # Extract tags
    tags = {}
    for tag_match in TAG_RE.finditer(full_text):
        tag_name = tag_match.group(1).lower()
        tag_value = tag_match.group(2)
        tags[tag_name] = tag_value

    # Clean description (remove tags)
    description = TAG_RE.sub("", full_text).strip()

    return Task(
        description=description,
        done=done,
        due=parse_date(tags["due"]) if "due" in tags else None,
        urgent="urgent" in tags,
        effort=tags.get("effort"),
        done_date=parse_date(tags["done"]) if "done" in tags else None,
        source_file=source,
        line_number=lineno,
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


def read_tasks(filepath: Path) -> list[Task]:
    """Read all tasks from one .md file."""
    tasks = []
    try:
        with open(filepath) as f:
            for i, line in enumerate(f, 1):
                task = parse_task_line(line, source=str(filepath), lineno=i)
                if task:
                    tasks.append(task)
    except FileNotFoundError:
        pass
    return tasks


def read_all_tasks(tasks_dir: Path = TASKS_DIR) -> list[Task]:
    """Read all tasks from all .md files in the tasks directory."""
    tasks = []
    for md_file in sorted(tasks_dir.glob("*.md")):
        tasks.extend(read_tasks(md_file))
    return tasks


def add_task_to_file(filepath: Path, task_line: str):
    """Append a task line under ## Active, creating the section/file if needed."""
    if not filepath.exists():
        heading = filepath.stem.replace("-", " ").title()
        filepath.write_text(f"# {heading}\n\n## Active\n{task_line}\n\n## Done\n")
        return

    lines = filepath.read_text().splitlines(keepends=True)

    # Find ## Active section and insert after it
    active_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "## active":
            active_idx = i
            break

    if active_idx is not None:
        # Find the end of the active section (next ## or end of file)
        insert_idx = active_idx + 1
        for i in range(active_idx + 1, len(lines)):
            if lines[i].strip().startswith("## "):
                # Insert before the blank line preceding the next section
                insert_idx = i
                break
            if lines[i].strip().startswith("- ["):
                insert_idx = i + 1  # after last task in section
        lines.insert(insert_idx, task_line + "\n")
    else:
        # No ## Active section, create one
        lines.append("\n## Active\n")
        lines.append(task_line + "\n")

    filepath.write_text("".join(lines))


def complete_task(filepath: Path, line_number: int):
    """Mark a task as done: flip checkbox, add @done(today), move to ## Done section."""
    lines = filepath.read_text().splitlines(keepends=True)
    idx = line_number - 1  # 0-indexed

    if idx < 0 or idx >= len(lines):
        return

    line = lines[idx]
    task = parse_task_line(line, source=str(filepath), lineno=line_number)
    if not task or task.done:
        return

    # Build completed line
    task.done = True
    task.done_date = date.today()
    completed_line = task_to_line(task) + "\n"

    # Remove from current position
    lines.pop(idx)

    # Find ## Done section
    done_idx = None
    for i, l in enumerate(lines):
        if l.strip().lower() == "## done":
            done_idx = i
            break

    if done_idx is not None:
        lines.insert(done_idx + 1, completed_line)
    else:
        lines.append("\n## Done\n")
        lines.append(completed_line)

    filepath.write_text("".join(lines))


def remove_task(filepath: Path, line_number: int) -> str | None:
    """Remove a task line from a file. Returns the removed line."""
    lines = filepath.read_text().splitlines(keepends=True)
    idx = line_number - 1

    if idx < 0 or idx >= len(lines):
        return None

    removed = lines.pop(idx)
    filepath.write_text("".join(lines))
    return removed.rstrip()


def client_to_filename(name: str) -> str:
    """Convert a client name to a slug filename: 'Acme Corp' -> 'acme-corp.md'."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug}.md"


def load_config() -> dict:
    """Load ~/.tasks/config.yaml."""
    config_path = TASKS_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def ensure_structure():
    """Create ~/.tasks/ directory structure and template config if missing."""
    TASKS_DIR.mkdir(exist_ok=True)
    (TASKS_DIR / "daily").mkdir(exist_ok=True)

    inbox = TASKS_DIR / "inbox.md"
    if not inbox.exists():
        inbox.write_text("# Inbox\n\n## Active\n\n## Done\n")

    config = TASKS_DIR / "config.yaml"
    if not config.exists():
        config.write_text(
            "# Task CLI Configuration\n\n"
            "# Email settings (for daily task delivery)\n"
            "smtp:\n"
            "  host: smtp.gmail.com\n"
            "  port: 587\n"
            "  username: your-email@gmail.com\n"
            "  password: your-app-password\n"
            "  recipient: your-email@gmail.com\n\n"
            "# Claude API key (or set ANTHROPIC_API_KEY env var)\n"
            "anthropic_api_key: \n\n"
            "# Daily schedule preferences\n"
            "daily:\n"
            "  available_hours: 6\n"
        )

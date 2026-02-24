#!/usr/bin/env python3
"""todo-schwesti: one-time migration from markdown files → Supabase.

Usage:
    python scripts/migrate.py              # Run migration
    python scripts/migrate.py --dry-run    # Preview without writing to DB
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.core.config import TASKS_DIR
from packages.core.markdown import read_tasks_from_file, get_project_heading


def get_all_md_files() -> list[Path]:
    """Get all .md files from ~/.tasks/, inbox first."""
    md_files = sorted(TASKS_DIR.glob("*.md"))
    inbox = TASKS_DIR / "inbox.md"
    ordered = []
    if inbox.exists():
        ordered.append(inbox)
    ordered.extend(f for f in md_files if f.name != "inbox.md")
    return ordered


def migrate(dry_run: bool = False):
    md_files = get_all_md_files()

    if not md_files:
        print("No .md files found in ~/.tasks/")
        return

    print(f"Found {len(md_files)} project files\n")

    all_projects = []
    all_tasks = []

    for i, md_file in enumerate(md_files):
        heading = get_project_heading(md_file)
        slug = md_file.stem
        tasks = read_tasks_from_file(md_file)

        active = [t for t in tasks if not t.done]
        done = [t for t in tasks if t.done]

        print(f"  {i+1}. {heading} ({slug}.md) — {len(active)} active, {len(done)} done")
        all_projects.append({"name": heading, "slug": slug, "position": i})
        for j, t in enumerate(tasks):
            all_tasks.append({
                "project_slug": slug,
                "description": t.description,
                "done": t.done,
                "due": t.due.isoformat() if t.due else None,
                "urgent": t.urgent,
                "effort": t.effort,
                "done_date": t.done_date.isoformat() if t.done_date else None,
                "position": j,
                "source": "migration",
            })

    print(f"\nTotal: {len(all_projects)} projects, {len(all_tasks)} tasks")

    if dry_run:
        print("\n[DRY RUN] No data written. Remove --dry-run to migrate.")
        return

    # Import DB only when actually migrating (requires Supabase connection)
    from packages.core.db import DB

    print("\nMigrating to Supabase...")

    # Create projects
    project_map = {}  # slug -> project_id
    for p in all_projects:
        project = DB.get_or_create_project(p["name"], p["slug"], p["position"])
        project_map[p["slug"]] = project.id
        print(f"  Project: {p['name']} -> {project.id}")

    # Create tasks
    created = 0
    for t in all_tasks:
        project_id = project_map.get(t["project_slug"])
        if not project_id:
            print(f"  WARN: No project for slug '{t['project_slug']}', skipping: {t['description']}")
            continue

        data = {
            "project_id": project_id,
            "description": t["description"],
            "done": t["done"],
            "urgent": t["urgent"],
            "position": t["position"],
            "source": t["source"],
        }
        if t["due"]:
            data["due"] = t["due"]
        if t["effort"]:
            data["effort"] = t["effort"]
        if t["done_date"]:
            data["done_date"] = t["done_date"]

        DB.insert_task_raw(data)
        created += 1

    print(f"\nDone! Created {created} tasks across {len(project_map)} projects.")
    print("Markdown files are untouched (backup).")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    migrate(dry_run=dry)

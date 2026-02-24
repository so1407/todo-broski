"""todo-schwesti: Supabase CRUD operations for tasks, projects, and daily plans."""

from __future__ import annotations

from datetime import date
from typing import Optional

from supabase import create_client, Client

from .config import get_supabase_url, get_supabase_key
from .models import Task, Project
from .markdown import parse_date

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(get_supabase_url(), get_supabase_key())
    return _client


class DB:
    """All Supabase operations for todo-schwesti."""

    # ── Projects ──────────────────────────────────────────────────────────

    @staticmethod
    def list_projects(include_archived: bool = False) -> list[Project]:
        client = _get_client()
        q = client.table("projects").select("*").order("position")
        if not include_archived:
            q = q.eq("archived", False)
        rows = q.execute().data
        return [Project.from_supabase(r) for r in rows]

    @staticmethod
    def get_project_by_slug(slug: str) -> Project | None:
        client = _get_client()
        rows = client.table("projects").select("*").eq("slug", slug).execute().data
        if rows:
            return Project.from_supabase(rows[0])
        return None

    @staticmethod
    def create_project(name: str, slug: str, position: int = 0) -> Project:
        client = _get_client()
        row = client.table("projects").insert({
            "name": name,
            "slug": slug,
            "position": position,
        }).execute().data[0]
        return Project.from_supabase(row)

    @staticmethod
    def get_or_create_project(name: str, slug: str, position: int = 0) -> Project:
        existing = DB.get_project_by_slug(slug)
        if existing:
            return existing
        return DB.create_project(name, slug, position)

    # ── Tasks ─────────────────────────────────────────────────────────────

    @staticmethod
    def list_tasks(
        project_slug: str | None = None,
        done: bool | None = None,
        urgent_only: bool = False,
    ) -> list[Task]:
        client = _get_client()
        q = client.table("tasks").select("*, projects(name, slug)").order("priority_score", desc=True).order("position")

        if done is not None:
            q = q.eq("done", done)
        if urgent_only:
            q = q.or_("urgent.eq.true,priority_score.gte.2")

        rows = q.execute().data

        tasks = []
        for r in rows:
            proj = r.pop("projects", {}) or {}
            t = Task.from_supabase(r, project_name=proj.get("name", ""), project_slug=proj.get("slug", ""))
            tasks.append(t)

        if project_slug:
            tasks = [t for t in tasks if t.project_slug == project_slug]

        return tasks

    @staticmethod
    def get_task(task_id: str) -> Task | None:
        client = _get_client()
        rows = client.table("tasks").select("*, projects(name, slug)").eq("id", task_id).execute().data
        if not rows:
            return None
        r = rows[0]
        proj = r.pop("projects", {}) or {}
        return Task.from_supabase(r, project_name=proj.get("name", ""), project_slug=proj.get("slug", ""))

    @staticmethod
    def add_task(
        description: str,
        project_slug: str | None = None,
        due: str | None = None,
        urgent: bool = False,
        effort: str | None = None,
        source: str = "cli",
    ) -> Task:
        client = _get_client()

        # Resolve project
        if project_slug:
            project = DB.get_project_by_slug(project_slug)
            if not project:
                project = DB.create_project(
                    name=project_slug.replace("-", " ").title(),
                    slug=project_slug,
                )
        else:
            project = DB.get_or_create_project("Inbox", "inbox")

        data = {
            "project_id": project.id,
            "description": description,
            "urgent": urgent,
            "source": source,
        }
        if due:
            parsed = parse_date(due)
            if parsed:
                data["due"] = parsed.isoformat()
        if effort:
            data["effort"] = effort

        row = client.table("tasks").insert(data).execute().data[0]
        return Task.from_supabase(row, project_name=project.name, project_slug=project.slug)

    @staticmethod
    def complete_task_by_id(task_id: str) -> Task | None:
        client = _get_client()
        rows = client.table("tasks").update({
            "done": True,
            "done_date": date.today().isoformat(),
        }).eq("id", task_id).execute().data
        if not rows:
            return None
        return Task.from_supabase(rows[0])

    @staticmethod
    def complete_task_by_search(search: str) -> str:
        """Fuzzy search + complete. Returns status message."""
        tasks = DB.list_tasks(done=False)
        search_lower = search.lower()
        matches = [t for t in tasks if search_lower in t.description.lower()]

        if not matches:
            return f"No open tasks matching '{search}'."

        if len(matches) == 1:
            DB.complete_task_by_id(matches[0].id)
            return f"Done: {matches[0].description}"

        lines = [f"{i+1}. {t.description} ({t.project_name})" for i, t in enumerate(matches[:10])]
        return "Multiple matches:\n\n" + "\n".join(lines) + "\n\nBe more specific."

    @staticmethod
    def update_task(task_id: str, **fields) -> Task | None:
        client = _get_client()
        # Convert date objects to ISO strings
        for key in ("due", "done_date"):
            if key in fields and isinstance(fields[key], date):
                fields[key] = fields[key].isoformat()
        rows = client.table("tasks").update(fields).eq("id", task_id).execute().data
        if not rows:
            return None
        return Task.from_supabase(rows[0])

    @staticmethod
    def move_task(task_id: str, project_slug: str) -> Task | None:
        project = DB.get_project_by_slug(project_slug)
        if not project:
            return None
        return DB.update_task(task_id, project_id=project.id)

    @staticmethod
    def delete_task(task_id: str) -> bool:
        client = _get_client()
        client.table("tasks").delete().eq("id", task_id).execute()
        return True

    @staticmethod
    def insert_task_raw(data: dict) -> dict:
        """Insert a raw task dict (for migration). Returns the created row."""
        client = _get_client()
        return client.table("tasks").insert(data).execute().data[0]

    # ── Daily Plans ───────────────────────────────────────────────────────

    @staticmethod
    def save_daily_plan(plan_date: date, content: str) -> dict:
        client = _get_client()
        row = client.table("daily_plans").upsert({
            "plan_date": plan_date.isoformat(),
            "content": content,
        }).execute().data[0]
        return row

    @staticmethod
    def get_daily_plan(plan_date: date) -> str | None:
        client = _get_client()
        rows = client.table("daily_plans").select("content").eq("plan_date", plan_date.isoformat()).execute().data
        if rows:
            return rows[0]["content"]
        return None

    # ── Stats (for board) ─────────────────────────────────────────────────

    @staticmethod
    def get_counts() -> dict:
        tasks = DB.list_tasks(done=False)
        return {
            "total": len(tasks),
            "overdue": sum(1 for t in tasks if t.is_overdue),
            "urgent": sum(1 for t in tasks if t.urgent and not t.is_overdue),
            "due_soon": sum(1 for t in tasks if t.is_due_soon),
        }

    # ── Week report ───────────────────────────────────────────────────────

    @staticmethod
    def get_tasks_completed_since(since: date) -> list[Task]:
        client = _get_client()
        rows = client.table("tasks").select("*, projects(name, slug)").eq("done", True).gte("done_date", since.isoformat()).execute().data
        tasks = []
        for r in rows:
            proj = r.pop("projects", {}) or {}
            tasks.append(Task.from_supabase(r, project_name=proj.get("name", ""), project_slug=proj.get("slug", "")))
        return tasks

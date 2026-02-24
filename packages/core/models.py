"""todo-schwesti: Task dataclass — bridge between Supabase rows and Python objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Task:
    """Unified task representation used across CLI, bot, and web."""

    id: str = ""
    project_id: str = ""
    project_name: str = ""
    project_slug: str = ""
    description: str = ""
    done: bool = False
    due: Optional[date] = None
    urgent: bool = False
    effort: Optional[str] = None
    position: int = 0
    priority_score: int = 0
    notes: Optional[str] = None
    recurring_rule: Optional[str] = None
    effort_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    source: str = "cli"
    done_date: Optional[date] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Legacy fields for backwards compat during migration
    source_file: str = ""
    line_number: int = 0
    raw_line: str = ""

    @property
    def is_overdue(self) -> bool:
        return self.due is not None and not self.done and self.due < date.today()

    @property
    def is_due_soon(self) -> bool:
        if self.due is None or self.done:
            return False
        days = (self.due - date.today()).days
        return 0 <= days <= 3

    @property
    def css_class(self) -> str:
        if self.is_overdue:
            return "overdue"
        if self.urgent:
            return "urgent"
        if self.is_due_soon:
            return "due-soon"
        return ""

    @classmethod
    def from_supabase(cls, row: dict, project_name: str = "", project_slug: str = "") -> Task:
        """Create a Task from a Supabase row dict."""
        due = None
        if row.get("due"):
            due = date.fromisoformat(row["due"])
        done_date = None
        if row.get("done_date"):
            done_date = date.fromisoformat(row["done_date"])

        return cls(
            id=row.get("id", ""),
            project_id=row.get("project_id", ""),
            project_name=project_name,
            project_slug=project_slug,
            description=row.get("description", ""),
            done=row.get("done", False),
            due=due,
            urgent=row.get("urgent", False),
            effort=row.get("effort"),
            position=row.get("position", 0),
            priority_score=row.get("priority_score", 0),
            notes=row.get("notes"),
            recurring_rule=row.get("recurring_rule"),
            effort_minutes=row.get("effort_minutes"),
            actual_minutes=row.get("actual_minutes"),
            source=row.get("source", "cli"),
            done_date=done_date,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_insert_dict(self) -> dict:
        """Convert to a dict for Supabase insert (no id, no timestamps)."""
        d = {
            "project_id": self.project_id,
            "description": self.description,
            "done": self.done,
            "urgent": self.urgent,
            "position": self.position,
            "source": self.source,
        }
        if self.due:
            d["due"] = self.due.isoformat()
        if self.effort:
            d["effort"] = self.effort
        if self.notes:
            d["notes"] = self.notes
        if self.done_date:
            d["done_date"] = self.done_date.isoformat()
        if self.effort_minutes is not None:
            d["effort_minutes"] = self.effort_minutes
        return d


@dataclass
class Project:
    """Project representation."""

    id: str = ""
    name: str = ""
    slug: str = ""
    color: Optional[str] = None
    position: int = 0
    archived: bool = False

    @classmethod
    def from_supabase(cls, row: dict) -> Project:
        return cls(
            id=row.get("id", ""),
            name=row.get("name", ""),
            slug=row.get("slug", ""),
            color=row.get("color"),
            position=row.get("position", 0),
            archived=row.get("archived", False),
        )

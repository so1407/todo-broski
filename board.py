"""HTML kanban board generation."""

from datetime import date, datetime
from pathlib import Path

from jinja2 import Template

from parser import read_tasks, get_project_heading

BOARD_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>Task Board</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f0f2f5;
    padding: 24px;
    color: #1a1a1a;
  }
  header {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 24px;
  }
  header h1 { font-size: 22px; font-weight: 600; }
  header .meta { color: #888; font-size: 13px; }
  .board {
    display: flex;
    gap: 16px;
    overflow-x: auto;
    align-items: flex-start;
    padding-bottom: 16px;
  }
  .column {
    background: #fff;
    border-radius: 10px;
    min-width: 280px;
    max-width: 320px;
    flex-shrink: 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .column-header {
    padding: 14px 16px 10px;
    font-weight: 600;
    font-size: 14px;
    border-bottom: 1px solid #f0f0f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .column-header .count {
    background: #e8e8e8;
    color: #666;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
  }
  .column-body { padding: 8px; }
  .card {
    padding: 10px 12px;
    margin: 6px 0;
    border-radius: 6px;
    border-left: 3px solid #ddd;
    background: #fafafa;
    font-size: 13px;
    line-height: 1.4;
  }
  .card.overdue { border-left-color: #e74c3c; background: #fef5f5; }
  .card.urgent { border-left-color: #f39c12; background: #fffcf5; }
  .card.due-soon { border-left-color: #3498db; background: #f5f9fe; }
  .card .desc { font-weight: 500; }
  .card .meta-row {
    display: flex; gap: 8px; margin-top: 4px;
    font-size: 11px; color: #888;
  }
  .card .meta-row .tag {
    background: #f0f0f0;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .card .meta-row .tag.urgent-tag { background: #fdebd0; color: #b7791f; }
  .card .meta-row .tag.overdue-tag { background: #fadbd8; color: #c0392b; }
  .done-section {
    border-top: 1px solid #f0f0f0;
    margin-top: 8px;
    padding-top: 4px;
  }
  .done-toggle {
    font-size: 12px; color: #aaa; cursor: pointer;
    padding: 6px 12px;
    user-select: none;
  }
  .done-toggle:hover { color: #666; }
  .done-tasks { display: none; padding: 0 8px 8px; }
  .done-tasks.open { display: block; }
  .done-card {
    padding: 6px 12px;
    margin: 4px 0;
    font-size: 12px;
    color: #aaa;
    text-decoration: line-through;
  }
</style>
</head>
<body>
<header>
  <h1>Task Board</h1>
  <span class="meta">Generated {{ generated_at }}</span>
</header>
<div class="board">
{% for col in columns %}
  <div class="column">
    <div class="column-header">
      {{ col.name }}
      <span class="count">{{ col.active | length }}</span>
    </div>
    <div class="column-body">
    {% for t in col.active %}
      <div class="card {{ t.css_class }}">
        <div class="desc">{{ t.description }}</div>
        <div class="meta-row">
          {% if t.is_overdue %}<span class="tag overdue-tag">overdue</span>{% endif %}
          {% if t.urgent and not t.is_overdue %}<span class="tag urgent-tag">urgent</span>{% endif %}
          {% if t.due %}<span class="tag">{{ t.due }}</span>{% endif %}
          {% if t.effort %}<span class="tag">{{ t.effort }}</span>{% endif %}
        </div>
      </div>
    {% endfor %}
    </div>
    {% if col.done %}
    <div class="done-section">
      <div class="done-toggle" onclick="this.nextElementSibling.classList.toggle('open')">
        {{ col.done | length }} completed
      </div>
      <div class="done-tasks">
        {% for t in col.done %}
        <div class="done-card">{{ t.description }}</div>
        {% endfor %}
      </div>
    </div>
    {% endif %}
  </div>
{% endfor %}
</div>
</body>
</html>
""")


def generate_board(tasks_dir: Path) -> Path:
    """Generate board.html from all task files. Returns the output path."""
    columns = []

    # Inbox first, then other projects sorted alphabetically
    md_files = sorted(tasks_dir.glob("*.md"))
    inbox = tasks_dir / "inbox.md"
    ordered = []
    if inbox.exists():
        ordered.append(inbox)
    ordered.extend(f for f in md_files if f.name != "inbox.md")

    for md_file in ordered:
        tasks = read_tasks(md_file)
        active = [t for t in tasks if not t.done]
        done = [t for t in tasks if t.done]

        # Sort active: overdue first, then urgent, then due date, then undated
        def sort_key(t):
            if t.is_overdue:
                return (0, t.due)
            if t.urgent:
                return (1, t.due or date.max)
            if t.due:
                return (2, t.due)
            return (3, date.max)

        active.sort(key=sort_key)

        # Add CSS class to each task
        for t in active:
            if t.is_overdue:
                t.css_class = "overdue"
            elif t.urgent:
                t.css_class = "urgent"
            elif t.is_due_soon:
                t.css_class = "due-soon"
            else:
                t.css_class = ""

        name = get_project_heading(md_file)
        columns.append({"name": name, "active": active, "done": done})

    html = BOARD_TEMPLATE.render(
        columns=columns,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    output = tasks_dir / "board.html"
    output.write_text(html)
    return output

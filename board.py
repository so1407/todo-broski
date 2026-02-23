"""HTML kanban board generation — mobile-friendly with Telegram deep links."""

import urllib.parse
from datetime import date, datetime
from pathlib import Path

from jinja2 import Template

from parser import read_tasks, get_project_heading, load_config

BOARD_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Task Board</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f0f2f5;
    color: #1a1a1a;
    padding: 16px;
  }
  header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
  }
  header h1 { font-size: 20px; font-weight: 600; }
  header .meta { color: #888; font-size: 12px; }

  /* ── Desktop: horizontal columns ── */
  .board {
    display: flex;
    gap: 14px;
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

  /* ── Mobile: stacked vertical ── */
  @media (max-width: 700px) {
    body { padding: 10px; }
    .board {
      flex-direction: column;
      overflow-x: visible;
    }
    .column {
      min-width: unset;
      max-width: unset;
      width: 100%;
    }
    header h1 { font-size: 18px; }
  }

  .column-header {
    padding: 12px 14px 10px;
    font-weight: 600;
    font-size: 14px;
    border-bottom: 1px solid #f0f0f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    background: #fff;
    border-radius: 10px 10px 0 0;
    z-index: 1;
  }
  .column-header .count {
    background: #e8e8e8;
    color: #666;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
  }
  .column-body { padding: 6px; }

  .card {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 12px;
    margin: 5px 0;
    border-radius: 8px;
    border-left: 3px solid #ddd;
    background: #fafafa;
    font-size: 14px;
    line-height: 1.4;
    -webkit-tap-highlight-color: transparent;
  }
  .card.overdue { border-left-color: #e74c3c; background: #fef5f5; }
  .card.urgent { border-left-color: #f39c12; background: #fffcf5; }
  .card.due-soon { border-left-color: #3498db; background: #f5f9fe; }

  .card .done-btn {
    flex-shrink: 0;
    width: 22px; height: 22px;
    border-radius: 50%;
    border: 2px solid #ccc;
    background: none;
    cursor: pointer;
    margin-top: 1px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
    text-decoration: none;
    color: transparent;
  }
  .card .done-btn:hover, .card .done-btn:active {
    border-color: #4caf50;
    background: #e8f5e9;
    color: #4caf50;
  }
  .card.overdue .done-btn { border-color: #e57373; }
  .card.urgent .done-btn { border-color: #ffb74d; }

  .card .card-content { flex: 1; min-width: 0; }
  .card .desc { font-weight: 500; }
  .card .meta-row {
    display: flex; gap: 6px; margin-top: 4px; flex-wrap: wrap;
    font-size: 11px; color: #888;
  }
  .card .meta-row .tag {
    background: #f0f0f0;
    padding: 1px 6px;
    border-radius: 3px;
    white-space: nowrap;
  }
  .card .meta-row .tag.urgent-tag { background: #fdebd0; color: #b7791f; }
  .card .meta-row .tag.overdue-tag { background: #fadbd8; color: #c0392b; }

  .done-section {
    border-top: 1px solid #f0f0f0;
    margin-top: 6px;
    padding-top: 4px;
  }
  .done-toggle {
    font-size: 12px; color: #aaa; cursor: pointer;
    padding: 8px 12px;
    user-select: none;
  }
  .done-toggle:hover { color: #666; }
  .done-tasks { display: none; padding: 0 6px 8px; }
  .done-tasks.open { display: block; }
  .done-card {
    padding: 6px 12px;
    margin: 3px 0;
    font-size: 12px;
    color: #aaa;
    text-decoration: line-through;
    border-radius: 6px;
  }

  /* Stats bar */
  .stats {
    display: flex; gap: 16px; margin-bottom: 14px;
    font-size: 12px; color: #888; flex-wrap: wrap;
  }
  .stats .stat { display: flex; align-items: center; gap: 4px; }
  .stats .dot { width: 8px; height: 8px; border-radius: 50%; }
  .stats .dot.red { background: #e74c3c; }
  .stats .dot.orange { background: #f39c12; }
  .stats .dot.blue { background: #3498db; }
  .stats .dot.gray { background: #bbb; }
</style>
</head>
<body>
<header>
  <h1>Task Board</h1>
  <span class="meta">{{ generated_at }}</span>
</header>
<div class="stats">
  {% if counts.overdue %}<span class="stat"><span class="dot red"></span> {{ counts.overdue }} overdue</span>{% endif %}
  {% if counts.urgent %}<span class="stat"><span class="dot orange"></span> {{ counts.urgent }} urgent</span>{% endif %}
  {% if counts.due_soon %}<span class="stat"><span class="dot blue"></span> {{ counts.due_soon }} due soon</span>{% endif %}
  <span class="stat"><span class="dot gray"></span> {{ counts.total }} total</span>
</div>
<div class="board">
{% for col in columns %}
{% if col.active or col.done %}
  <div class="column">
    <div class="column-header">
      {{ col.name }}
      <span class="count">{{ col.active | length }}</span>
    </div>
    <div class="column-body">
    {% for t in col.active %}
      <div class="card {{ t.css_class }}">
        <a class="done-btn" href="{{ t.done_link }}" title="Mark done">✓</a>
        <div class="card-content">
          <div class="desc">{{ t.description }}</div>
          <div class="meta-row">
            {% if t.is_overdue %}<span class="tag overdue-tag">overdue</span>{% endif %}
            {% if t.urgent and not t.is_overdue %}<span class="tag urgent-tag">urgent</span>{% endif %}
            {% if t.due %}<span class="tag">{{ t.due }}</span>{% endif %}
            {% if t.effort %}<span class="tag">{{ t.effort }}</span>{% endif %}
          </div>
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
{% endif %}
{% endfor %}
</div>
</body>
</html>
""")


def _make_done_link(task, bot_username: str) -> str:
    """Create a Telegram deep link to mark a task done."""
    # Use first 3+ distinctive words as search term
    words = task.description.split()
    search = " ".join(words[:4]) if len(words) > 4 else task.description
    text = f"/done {search}"
    encoded = urllib.parse.quote(text)
    return f"https://t.me/{bot_username}?text={encoded}"


def generate_board(tasks_dir: Path) -> Path:
    """Generate board.html from all task files. Returns the output path."""
    cfg = load_config()
    bot_username = cfg.get("telegram", {}).get("bot_username", "sophies_todos_bot")

    columns = []
    counts = {"overdue": 0, "urgent": 0, "due_soon": 0, "total": 0}

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

        def sort_key(t):
            if t.is_overdue:
                return (0, t.due)
            if t.urgent:
                return (1, t.due or date.max)
            if t.due:
                return (2, t.due)
            return (3, date.max)

        active.sort(key=sort_key)

        for t in active:
            counts["total"] += 1
            if t.is_overdue:
                t.css_class = "overdue"
                counts["overdue"] += 1
            elif t.urgent:
                t.css_class = "urgent"
                counts["urgent"] += 1
            elif t.is_due_soon:
                t.css_class = "due-soon"
                counts["due_soon"] += 1
            else:
                t.css_class = ""
            t.done_link = _make_done_link(t, bot_username)

        name = get_project_heading(md_file)
        columns.append({"name": name, "active": active, "done": done})

    html = BOARD_TEMPLATE.render(
        columns=columns,
        counts=counts,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    output = tasks_dir / "board.html"
    output.write_text(html)
    return output

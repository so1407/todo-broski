"""HTML kanban board generation — mobile-friendly with inline task completion."""

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
<title>Task Board</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f0f2f5;
    color: #1a1a1a;
    padding: 16px;
    max-width: 100vw;
    overflow-x: hidden;
  }
  header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
  }
  header h1 { font-size: 20px; font-weight: 600; }
  header .meta { color: #888; font-size: 12px; }

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

  @media (max-width: 700px) {
    body { padding: 10px; }
    .board { flex-direction: column; overflow-x: visible; }
    .column { min-width: unset; max-width: unset; width: 100%; }
    header h1 { font-size: 18px; }
    .card { font-size: 15px; padding: 12px 14px; }
    .card .done-btn { width: 26px; height: 26px; }
  }

  .column-header {
    padding: 12px 14px 10px;
    font-weight: 600; font-size: 14px;
    border-bottom: 1px solid #f0f0f0;
    display: flex; justify-content: space-between; align-items: center;
    position: sticky; top: 0;
    background: #fff; border-radius: 10px 10px 0 0; z-index: 1;
  }
  .column-header .count {
    background: #e8e8e8; color: #666;
    font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 500;
  }
  .column-body { padding: 6px; }

  .card {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 10px 12px; margin: 5px 0; border-radius: 8px;
    border-left: 3px solid #ddd; background: #fafafa;
    font-size: 14px; line-height: 1.4;
    transition: all 0.3s ease;
  }
  .card.overdue { border-left-color: #e74c3c; background: #fef5f5; }
  .card.urgent { border-left-color: #f39c12; background: #fffcf5; }
  .card.due-soon { border-left-color: #3498db; background: #f5f9fe; }
  .card.completing {
    opacity: 0.4; transform: scale(0.97);
    text-decoration: line-through; color: #aaa;
  }
  .card.completed {
    opacity: 0; max-height: 0; padding: 0; margin: 0; overflow: hidden;
    border: none;
  }

  .card .done-btn {
    flex-shrink: 0; width: 22px; height: 22px;
    border-radius: 50%; border: 2px solid #ccc;
    background: none; cursor: pointer; margin-top: 1px;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.15s; font-size: 12px; color: transparent;
    -webkit-tap-highlight-color: transparent;
  }
  .card .done-btn:hover, .card .done-btn:active {
    border-color: #4caf50; background: #e8f5e9; color: #4caf50;
  }
  .card .done-btn.checked {
    border-color: #4caf50; background: #4caf50; color: #fff;
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
    background: #f0f0f0; padding: 1px 6px; border-radius: 3px; white-space: nowrap;
  }
  .card .meta-row .tag.urgent-tag { background: #fdebd0; color: #b7791f; }
  .card .meta-row .tag.overdue-tag { background: #fadbd8; color: #c0392b; }

  .done-section { border-top: 1px solid #f0f0f0; margin-top: 6px; padding-top: 4px; }
  .done-toggle {
    font-size: 12px; color: #aaa; cursor: pointer;
    padding: 8px 12px; user-select: none;
  }
  .done-toggle:hover { color: #666; }
  .done-tasks { display: none; padding: 0 6px 8px; }
  .done-tasks.open { display: block; }
  .done-card {
    padding: 6px 12px; margin: 3px 0; font-size: 12px;
    color: #aaa; text-decoration: line-through; border-radius: 6px;
  }

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

  .toast {
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: #333; color: #fff; padding: 10px 20px; border-radius: 8px;
    font-size: 14px; opacity: 0; transition: opacity 0.3s; z-index: 100;
    pointer-events: none;
  }
  .toast.show { opacity: 1; }
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
      <span class="count" id="count-{{ loop.index }}">{{ col.active | length }}</span>
    </div>
    <div class="column-body">
    {% for t in col.active %}
      <div class="card {{ t.css_class }}" id="task-{{ t.source_file | replace('/', '-') }}-{{ t.line_number }}">
        <button class="done-btn"
                onclick="markDone(this, '{{ t.source_file }}', {{ t.line_number }})"
                title="Mark done">✓</button>
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
<div class="toast" id="toast"></div>
<script>
const API = window.location.origin;

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

async function markDone(btn, sourceFile, lineNumber) {
  const card = btn.closest('.card');
  if (card.classList.contains('completing')) return;

  // Immediate visual feedback
  btn.classList.add('checked');
  card.classList.add('completing');

  try {
    const res = await fetch(API + '/api/done', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({source_file: sourceFile, line_number: lineNumber})
    });
    const data = await res.json();
    if (data.ok) {
      showToast('✓ Done!');
      setTimeout(() => {
        card.classList.add('completed');
        // Update count
        const col = card.closest('.column');
        const count = col.querySelector('.count');
        count.textContent = parseInt(count.textContent) - 1;
      }, 400);
    } else {
      card.classList.remove('completing');
      btn.classList.remove('checked');
      showToast('Error: ' + (data.error || 'unknown'));
    }
  } catch(e) {
    card.classList.remove('completing');
    btn.classList.remove('checked');
    showToast('Could not connect to server');
  }
}

// Auto-refresh every 60s (only if no pending actions)
setInterval(() => {
  if (!document.querySelector('.completing')) {
    window.location.reload();
  }
}, 60000);
</script>
</body>
</html>
""")


def generate_board(tasks_dir: Path) -> Path:
    """Generate board.html from all task files. Returns the output path."""
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

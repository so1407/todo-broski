# ToDo Schwesti

Personal task management system: CLI + Telegram bot + real-time kanban board. Supabase as the single source of truth, deployed across Vercel and Railway.

## Architecture

```
Supabase (PostgreSQL + real-time)
  ├── Vercel    → Next.js kanban board (any device, real-time)
  ├── Railway   → Telegram bot (24/7, natural language)
  ├── CLI       → local terminal (fast capture)
  └── Markdown  → export/backup (version-controlled)
```

All clients read and write from the same Supabase database. Changes from any source (CLI, bot, board) appear everywhere in real-time.

## Repo Structure

```
todo-schwesti/
  packages/
    core/                  # Shared Python library
      config.py            # Config: env vars → config.yaml fallback
      db.py                # All Supabase CRUD (DB class)
      models.py            # Task + Project dataclasses
      markdown.py          # Markdown parsing + export
    web/                   # Next.js kanban board (Vercel)
      src/
        app/
          layout.tsx       # Root layout (Inter font, metadata)
          page.tsx         # Entry point (dynamic import, no SSR)
          globals.css      # Tailwind import
        components/
          Board.tsx        # Main board: columns, search, drag & drop
          Column.tsx       # Project column (droppable target)
          TaskCard.tsx     # Task card (draggable, editable, completable)
          StatsBar.tsx     # Overdue/urgent/due-soon/total counters
          AddTaskDialog.tsx # Modal for adding tasks
        lib/
          supabase.ts      # Supabase client + TypeScript types
          hooks.ts         # React hooks (useProjects, useTasks) + CRUD functions
  scripts/
    setup.sql              # Database schema (tables, triggers, indexes)
    migrate.py             # One-time markdown → Supabase migration
  task_cli.py              # CLI entry point (Click)
  ai.py                    # Claude AI: daily planning + inbox sorting
  telegram_bot.py          # Telegram bot entry point
  Dockerfile               # Railway deployment (Python 3.11)
  railway.toml             # Railway config
  requirements.txt         # Python dependencies
```

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and run the contents of `scripts/setup.sql`
3. This creates:
   - `projects` — task groups (name, slug, color, position)
   - `tasks` — individual tasks (description, done, due, urgent, effort, priority_score, etc.)
   - `daily_plans` — AI-generated daily schedules
   - `task_activity` — audit log (created, completed, moved, updated)
   - Triggers for auto `updated_at`, auto `priority_score` computation, and activity logging
   - Realtime publication on `tasks` and `projects`

### 2. Configuration

ToDo Schwesti reads config from **environment variables first**, then falls back to `~/.tasks/config.yaml`.

**Environment variables** (used by Railway/Vercel):

| Variable | Used by | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | CLI, Bot | Supabase project URL |
| `SUPABASE_KEY` | CLI, Bot | Supabase anon key |
| `ANTHROPIC_API_KEY` | CLI, Bot | Claude API key (for AI features) |
| `TELEGRAM_TOKEN` | Bot | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Bot | Your Telegram chat ID (authorization) |
| `VERCEL_URL` | Bot | Board URL (sent by `/board` command) |
| `NEXT_PUBLIC_SUPABASE_URL` | Web | Supabase project URL (client-side) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Web | Supabase anon key (client-side) |

**Config file** (`~/.tasks/config.yaml`, for local CLI use):

```yaml
supabase:
  url: https://your-project.supabase.co
  key: your-anon-key

anthropic_api_key: sk-ant-...

telegram:
  token: "your-bot-token"
  chat_id: 123456789
  bot_username: your_bot

vercel_url: https://your-app.vercel.app

daily:
  available_hours: 6
```

### 3. Local CLI Setup

```bash
git clone https://github.com/so1407/todo-schwesti.git
cd todo-schwesti
pip install -r requirements.txt

# Create config
mkdir -p ~/.tasks
nano ~/.tasks/config.yaml   # add supabase url + key at minimum

# Add shell alias
echo "alias task='python3 $(pwd)/task_cli.py'" >> ~/.zshrc
source ~/.zshrc
```

### 4. Migrate Existing Tasks (optional)

If you have existing markdown task files in `~/.tasks/`:

```bash
python scripts/migrate.py --dry-run   # preview what will be migrated
python scripts/migrate.py             # run the migration
```

Markdown format expected: `- [ ] Task description @due(2025-03-01) @urgent @effort(2h)`

### 5. Deploy Web Board (Vercel)

1. Import repo on [vercel.com](https://vercel.com)
2. Set **Root Directory** to `packages/web`
3. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Deploy

### 6. Deploy Telegram Bot (Railway)

1. Create a new project on [railway.app](https://railway.app)
2. Connect your GitHub repo
3. Add environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ANTHROPIC_API_KEY`
4. Railway will use the `Dockerfile` at the repo root
5. Deploy

To get your Telegram chat ID: message your bot, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`

## Usage

### CLI

```bash
task add "Fix landing page" --client trewit --due friday --urgent --effort 2h
task add "Quick thought"                # goes to Inbox
task list                               # all open tasks, grouped by project
task list --client trewit               # filter by project
task list --urgent                      # urgent + overdue only
task done "landing"                     # fuzzy-match complete
task inbox                              # show unsorted inbox tasks
task sort                               # AI sorts inbox → correct projects
task daily                              # AI generates today's task list
task daily --send                       # + sends via Telegram
task week                               # weekly report (done + still open)
task week --send                        # + sends via Telegram
task board                              # opens kanban board in browser
task export                             # Supabase → markdown backup files
task export -o ./backup                 # export to custom directory
```

### Telegram Bot

Chat naturally — the bot uses Claude to parse your messages:

```
"add fix login for trewit, urgent, due friday"
"done with the invoice"
"what's on my list?"
"urgent stuff"
"daily"
"weekly review"
"board"
```

Slash commands: `/start`, `/add`, `/done`, `/list`, `/urgent`, `/daily`, `/week`, `/board`

### Web Board

Real-time kanban at your Vercel URL. Features:

- **Drag & drop** — grab the `⠿` handle to move tasks between project columns
- **Click to complete** — hit the circle checkbox
- **Inline edit** — click any task description to edit it
- **Add tasks** — `+ Add` button with project picker, due date, urgency, effort
- **Search** — filter tasks across all projects
- **Status colors** — red (overdue), orange (urgent), blue (due soon)
- **Stats bar** — live counts of overdue, urgent, due-soon, total
- **Collapsible done** — completed tasks hidden by default per column
- **Mobile responsive** — columns stack vertically on small screens

## Database Schema

### projects

| Column | Type | Description |
|--------|------|-------------|
| id | uuid (PK) | Auto-generated |
| name | text | Display name (e.g. "Trewit") |
| slug | text (unique) | URL-safe name (e.g. "trewit") |
| color | text | Optional color code |
| position | int | Sort order |
| archived | boolean | Hide from active views |

### tasks

| Column | Type | Description |
|--------|------|-------------|
| id | uuid (PK) | Auto-generated |
| project_id | uuid (FK) | References projects.id |
| description | text | Task text |
| done | boolean | Completion status |
| due | date | Due date (nullable) |
| urgent | boolean | Urgency flag |
| effort | text | Estimate, e.g. "2h", "30m" |
| position | int | Sort order within project |
| priority_score | int | Auto-computed: 3=overdue, 2=urgent, 1=due-soon, 0=normal |
| notes | text | Additional notes |
| recurring_rule | text | For future recurring tasks |
| effort_minutes | int | Estimated effort in minutes |
| actual_minutes | int | Tracked actual effort |
| source | text | "cli", "telegram", "web" |
| done_date | date | When completed |
| created_at | timestamptz | Auto-set |
| updated_at | timestamptz | Auto-updated by trigger |

### daily_plans

| Column | Type | Description |
|--------|------|-------------|
| id | uuid (PK) | Auto-generated |
| plan_date | date (unique) | One plan per day |
| content | text | AI-generated markdown |

### task_activity

| Column | Type | Description |
|--------|------|-------------|
| id | uuid (PK) | Auto-generated |
| task_id | uuid (FK) | References tasks.id |
| action | text | "created", "completed", "updated", "moved" |
| details | jsonb | Context (description, from/to project) |
| created_at | timestamptz | When it happened |

## AI Features

Uses Claude (Anthropic API) for two features:

- **`task daily`** — Picks a realistic day's work from your open tasks, respecting due dates, urgency, and effort estimates. Saves to Supabase and optionally sends via Telegram.
- **`task sort`** — Reads inbox tasks, matches them to existing projects (or suggests new ones), and moves them automatically.
- **Telegram NLP** — The bot parses natural language messages into structured actions (add, done, list, etc.) using Claude Haiku.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Database | Supabase (PostgreSQL + Realtime) |
| Web board | Next.js 16, TypeScript, Tailwind CSS 4, @dnd-kit |
| Telegram bot | python-telegram-bot |
| CLI | Click (Python) |
| AI | Anthropic Claude API |
| Bot hosting | Railway (Docker) |
| Web hosting | Vercel |

## License

Do whatever you want with it.

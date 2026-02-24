# ToDo Schwesti

Personal task management: CLI + Telegram bot + real-time kanban board. Supabase as the source of truth, deployable anywhere.

## Architecture

```
Supabase (PostgreSQL + real-time)    ← source of truth
  ├── Vercel (Next.js kanban board)  ← accessible from any device
  ├── Railway (Telegram bot, 24/7)   ← no laptop dependency
  ├── CLI (local, talks to Supabase) ← fast terminal capture
  └── Markdown export (backup only)  ← version-controlled snapshots
```

## Quick start

```bash
git clone https://github.com/so1407/todo-schwesti.git
cd todo-schwesti

pip install -r requirements.txt

# Edit config with your Supabase + API keys
nano ~/.tasks/config.yaml

# Add the shell alias
echo "alias task='python3 $(pwd)/task_cli.py'" >> ~/.zshrc
source ~/.zshrc
```

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Run `scripts/setup.sql` in the SQL Editor
3. Add credentials to `~/.tasks/config.yaml`:

```yaml
supabase:
  url: https://your-project.supabase.co
  key: your-anon-key
```

### 2. Migrate existing tasks

```bash
python scripts/migrate.py --dry-run   # preview
python scripts/migrate.py             # run for real
```

### 3. Anthropic API key

```yaml
anthropic_api_key: sk-ant-...
```

### 4. Telegram bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Add to config:

```yaml
telegram:
  token: "your-bot-token"
  chat_id: your-chat-id
  bot_username: your_bot
```

### 5. Deploy

- **Web board:** Deploy `packages/web/` to Vercel. Set `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- **Telegram bot:** Deploy to Railway. Set `SUPABASE_URL`, `SUPABASE_KEY`, `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`.

Add the board URL to config:

```yaml
vercel_url: https://your-app.vercel.app
```

## Usage

### CLI

```bash
task add "Fix landing page" --client "Acme" --due friday --urgent --effort 2h
task add "Quick thought"              # goes to inbox
task list                             # all open tasks
task list --urgent                    # urgent only
task done "landing"                   # fuzzy-match complete
task inbox                            # unsorted tasks
task sort                             # AI sorts inbox into projects
task daily                            # AI generates daily list
task daily --send                     # + sends via Telegram
task board                            # opens kanban board
task export                           # Supabase → markdown backup
```

### Telegram bot

Chat naturally:

```
"add fix login for trewit, urgent, due friday"
"done with the invoice"
"what's on my list?"
"urgent stuff"
"daily"
"board"
```

Slash commands: `/add`, `/done`, `/list`, `/urgent`, `/daily`, `/week`, `/board`

### Web board

Real-time kanban at your Vercel URL. Click-to-complete, inline edit, search, mobile-responsive.

## Repo structure

```
todo-schwesti/
  packages/
    core/           # Shared Python: db.py, config.py, models.py, markdown.py
    cli/            # CLI setup
    bot/            # Telegram bot (Railway deployment)
    web/            # Next.js board (Vercel deployment)
  scripts/
    migrate.py      # Markdown → Supabase migration
    setup.sql       # Database schema
  task_cli.py       # CLI entry point
  ai.py             # Claude AI integration
  telegram_bot.py   # Telegram bot entry point
```

## License

Do whatever you want with it.

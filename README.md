# todo-broski

Personal task management CLI + Telegram bot + kanban board. Markdown files as source of truth, AI-powered daily planning, zero-maintenance by design.

## Why

Kanban boards die when you're busy — which is exactly when you need them. This tool keeps the overhead near zero:

- **Capture** a task in 3 seconds (CLI or Telegram)
- **AI sorts** your inbox into projects
- **AI generates** a realistic daily to-do list at 18:00
- **Telegram bot** sends it to your phone
- All data is just markdown files you can edit by hand

## Quick start

```bash
# Clone
git clone https://github.com/so1407/todo-broski.git
cd todo-broski

# Install dependencies
pip install -r requirements.txt

# First run creates ~/.tasks/ with template config
python task_cli.py list

# Edit config with your API keys
nano ~/.tasks/config.yaml

# Add the shell alias
echo "alias task='python3 $(pwd)/task_cli.py'" >> ~/.zshrc
source ~/.zshrc
```

## Setup

### 1. Anthropic API key

Get one at [console.anthropic.com](https://console.anthropic.com). Add to `~/.tasks/config.yaml`:

```yaml
anthropic_api_key: sk-ant-...
```

### 2. Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Send any message to your new bot
3. Add to config:

```yaml
telegram:
  token: "your-bot-token"
  chat_id: your-chat-id  # get from https://api.telegram.org/bot<TOKEN>/getUpdates
  bot_username: your_bot_username
```

### 3. Start the bot + web server

```bash
python telegram_bot.py
```

This runs both:
- Telegram bot (natural language task management)
- Web board at `http://localhost:8347`

To run as a background service on macOS, create a launchd plist (see below).

### 4. Auto-daily at 18:00 (optional)

Create `~/Library/LaunchAgents/com.tasks.daily-list.plist` for automatic daily list generation and Telegram delivery.

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
task board                            # opens HTML kanban in browser
```

### Telegram bot

Just chat naturally — no slash commands needed:

```
"add fix login for trewit, urgent, due friday"
"done with the invoice"
"what's on my list?"
"urgent stuff"
"daily"
```

Slash commands work too: `/add`, `/done`, `/list`, `/urgent`, `/daily`, `/board`

### Web board

Open `http://localhost:8347` in your browser. Click the circle next to any task to mark it done — no page reload needed.

## Task format

Tasks live in markdown files in `~/.tasks/`, one per project:

```markdown
# Acme Corp

## Active
- [ ] Write Q1 proposal @due(2026-02-25) @urgent @effort(2h)
- [ ] Send invoice @effort(15m)

## Done
- [x] Kick-off meeting @done(2026-02-20)
```

Three tags: `@due(YYYY-MM-DD)`, `@urgent`, `@effort(Xh/Xm)`. That's it.

## Architecture

```
~/.tasks/                  # Your data (markdown files)
    config.yaml            # API keys, preferences
    inbox.md               # Quick capture
    acme-corp.md           # One file per project
    daily/2026-02-23.md    # AI-generated daily lists

~/task-cli/                # The tool (4 Python files)
    parser.py              # Markdown parsing + file ops
    task_cli.py            # CLI commands (click)
    ai.py                  # Claude API integration
    board.py               # HTML kanban generation
    telegram_bot.py        # Telegram bot + web server
```

## macOS launchd setup

**Telegram bot + web server** (`~/Library/LaunchAgents/com.tasks.telegram-bot.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tasks.telegram-bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/task-cli/telegram_bot.py</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>WorkingDirectory</key><string>/path/to/task-cli</string>
</dict>
</plist>
```

**Daily list at 18:00** (`~/Library/LaunchAgents/com.tasks.daily-list.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tasks.daily-list</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/task-cli/task_cli.py</string>
        <string>daily</string>
        <string>--send</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    <key>WorkingDirectory</key><string>/path/to/task-cli</string>
</dict>
</plist>
```

Load with: `launchctl load ~/Library/LaunchAgents/com.tasks.*.plist`

## License

Do whatever you want with it.

<div align="center">

# 🛡️ Aegis

**Production-grade Telegram Group Management Bot**

[![Build: Passing](https://github.com/mrsehajofficial/aegis/actions/workflows/tests.yml/badge.svg)](https://github.com/mrsehajofficial/aegis/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21+-green.svg)](https://github.com/python-telegram-bot/python-telegram-bot)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-orange.svg)](https://www.sqlalchemy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

*Aegis — the emerald guardian of your Telegram groups. Deterministic, dependable protection.*

[Features](#features) •
[Installation](#installation) •
[Configuration](#configuration) •
[Commands](#commands) •
[Architecture](#architecture) •
[Contributing](#contributing)

</div>

---

## 📋 Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Commands Reference](#commands-reference)
- [Architecture](#architecture)
- [Database Schema](#database-schema)
- [Development](#development)
- [Deployment](#deployment)
- [Contributing](#contributing)
---

## ✨ Features

### 🔨 Moderation
| Feature | Description |
|---------|-------------|
| **Ban/Unban** | Permanent removal with optional reason |
| **Kick** | Remove user without ban (can rejoin) |
| **Mute/Unmute** | Restrict messaging with flexible durations |
| **Warnings** | Configurable warn limits with auto-action |
| **Purge** | Bulk delete messages from a point onward |
| **Pin/Unpin** | Manage pinned messages with silent option |

### 🛡️ Protection
| Feature | Description |
|---------|-------------|
| **Anti-Flood** | Sliding window rate limiting per user |
| **Anti-Spam** | URL/domain detection and auto-action |
| **Lock Types** | Restrict media, stickers, links, etc. |
| **Blacklist** | Banned words with auto-delete |
| **Group Protection** | Automated enforcement rules |

### 📝 Content Management
| Feature | Description |
|---------|-------------|
| **Filters** | Keyword-triggered auto-responses |
| **Notes** | Saved text snippets retrievable by keyword |
| **Welcome/Goodbye** | Configurable join/leave messages |
| **Rules** | Group rules display and management |

### 💼 Telegram Business Automation
| Feature | Description |
|---------|-------------|
| **Business Connection** | Connect your Telegram Business account via Settings → Telegram Business → Chatbots |
| **Auto-Reply** | Keyword-triggered replies sent on your behalf in private chats |
| **Greeting Message** | Automatic welcome message for first-time contacts |
| **Away / Out-of-Office** | Fallback reply sent when no keyword matches (15-min cooldown) |
| **Keyword Rules** | Add unlimited trigger/response pairs with `contains` or `exact` matching |
| **Inline Dashboard** | Toggle all features live from `/biz` without any config files |
| **Safety Guards** | Never replies to your own messages; 2-second anti-loop debounce |

### 📊 Administration
| Feature | Description |
|---------|-------------|
| **Reports** | User reporting system with admin alerts |
| **Audit Logs** | Full moderation history |
| **Admin Tools** | Role-based access control |
| **Settings** | Per-group configuration |

---

## 📦 Prerequisites

- **Python** 3.11 or higher
- **pip** or **uv** package manager
- **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)
- **Database**: SQLite (built-in) or PostgreSQL 12+
- *(Optional)* Telegram Business subscription to use the `/biz` auto-reply features

---

## 🚀 Installation

### Option 1: Quick Start (Recommended)

```bash
# Clone the repository
git clone https://github.com/mrsehajofficial/aegis.git
cd aegis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Run interactive setup
python -m app.setup
```

### Option 2: Using `uv` (Fast)

```bash
# Clone the repository
git clone https://github.com/mrsehajofficial/aegis.git
cd aegis

# Install dependencies with uv
uv sync --all-extras

# Run interactive setup
uv run python -m app.setup
```

### Option 3: Docker Compose

```bash
# Clone the repository
git clone https://github.com/mrsehajofficial/aegis.git
cd aegis

# Build and run
docker compose up --build -d
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Required
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Database (SQLite by default, PostgreSQL recommended for production)
DATABASE_URL=sqlite+aiosqlite:///./aegis.db
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/aegis

# Optional
LOG_LEVEL=INFO
SUPER_ADMIN_IDS=123456789,987654321
BOT_NAME=Aegis
WARN_ACTION=mute  # mute | ban | kick
```

### Database Options

| Database | URL Format | Use Case |
|----------|------------|----------|
| **SQLite** | `sqlite+aiosqlite:///./aegis.db` | Development, small groups |
| **PostgreSQL** | `postgresql+asyncpg://user:pass@host/db` | Production, high traffic |

### First-Time Setup

Run the interactive wizard:

```bash
python -m app.setup
```

The wizard will:
1. Prompt for your bot token (hidden input)
2. Configure database connection
3. Set super admin user IDs
4. Set bot display name
5. Configure warn action
6. Write `.env` with `600` permissions
---

## 🎮 Commands Reference

### Moderation (Admins Only)
```
/ban [reply|@user] [reason]     — Ban a member permanently
/unban [reply|@user]             — Remove a ban
/kick [reply|@user] [reason]     — Remove without ban
/mute [reply|@user] [time]       — Mute (e.g., 1h, 30m, 1d)
/unmute [reply|@user]            — Remove mute
/warn [reply|@user] [reason]     — Issue a warning
/warnings [reply|@user]          — View warning count
/resetwarns [reply|@user]        — Clear all warnings
/purge                           — Delete from replied message onward
/pin                             — Pin the replied message
/unpin                           — Unpin the current message
```

### Group Settings (Admins Only)
```
/rules                           — Display group rules
/setrules [text]                 — Set group rules
/welcome                         — Show the welcome message
/setwelcome on|off|[text]        — Toggle or set the welcome message
/goodbye                         — Show the goodbye message
/setgoodbye on|off|[text]        — Toggle or set the goodbye message
/settings                        — View all group settings
/setwarnlimit N                  — Set warn limit (1-20)
```

### Protection (Admins Only)
```
/setantiflood on|off             — Toggle anti-flood
/setantispam on|off              — Toggle anti-spam
/lock [type]                     — Lock content type
/unlock [type]                   — Unlock content type
/locktypes                       — List available lock types
/addblacklist [word]             — Add banned word
/blacklist                       — List banned words
/rmblacklist [word]              — Remove banned word
```

### Notes (Admins Only)
```
/save [keyword] [content]        — Save a note
/get [keyword]                   — Retrieve a note
/clear [keyword]                 — Delete a note
/notes                           — List all notes
```

### Filters (Admins Only)
```
/filter [keyword] [response]     — Add auto-reply filter
/filters                         — List active filters
/stop [keyword]                  — Remove a filter
```

### Reports
```
/report                          — Report message to admins (reply)
/setreports on|off               — Toggle reports (admins only)
```

### Information
```
/id                              — Show chat/user/message IDs
/info [reply|@user|id]           — User profile and role
/admins                          — List group administrators
/logs                            — Recent moderation log (admins only)
```

### 💼 Telegram Business (Private Chat)
> Requires a Telegram Business subscription. Connect the bot once via
> **Telegram Settings → Telegram Business → Chatbots**.

```
/biz                             — Open the Business automation dashboard
/business                        — Alias for /biz
/bizrules                        — List all active keyword auto-replies
/bizadd <keyword> <response>     — Add or update a keyword rule
/bizdel <keyword>                — Remove a keyword rule
/bizgreeting [text|off]          — Set or toggle the greeting message
/bizaway [text|off]              — Set or toggle the away/OOO message
/bizstatus                       — Connection diagnostics
```

**How it works:**
1. Connect the bot to your Telegram Business account once (Settings → Telegram Business → Chatbots, grant "Reply to messages" permission).
2. Use `/bizadd pricing Our plans start at $99/mo.` to teach the bot your responses.
3. When a customer's message matches a keyword, Aegis replies instantly *on your behalf* via `business_connection_id` — it appears as a message from you, not from the bot.
4. Greeting and away messages handle first-time contacts and off-hours automatically.

---

## 🏗️ Architecture

```
aegis/
├── app/
│   ├── __init__.py          # Application entry
│   ├── main.py              # Bot startup and polling
│   ├── setup.py             # Interactive setup wizard
│   ├── anti_spam/           # Anti-spam detection
│   │   ├── detector.py      # Spam pattern detection
│   │   ├── flood.py         # Flood control (sliding window)
│   │   └── actions.py       # Moderation actions
│   ├── bot/
│   │   ├── application.py   # Telegram Application builder
│   │   ├── handlers/        # Command handlers
│   │   │   ├── business.py  # Telegram Business auto-reply
│   │   │   ├── commands.py  # Core commands
│   │   │   ├── moderation.py # Ban/mute/warn
│   │   │   ├── filters.py   # Auto-reply filters
│   │   │   ├── welcome.py   # Welcome/goodbye/rules
│   │   │   ├── notes.py     # Note management
│   │   │   ├── reports.py   # Report system
│   │   │   └── ...
│   │   ├── helpers/         # Utility functions
│   │   └── middleware/      # Auth & throttling
│   ├── config/              # Configuration
│   │   ├── settings.py      # Pydantic settings
│   │   └── logging.py       # Logging configuration
│   ├── database/            # Database layer
│   │   ├── connection.py    # Session management
│   │   ├── models/          # SQLAlchemy models
│   │   └── repositories/    # Data access layer
│   ├── moderation/          # Moderation logic
│   └── services/            # Business logic
│       ├── business.py      # Telegram Business service layer
│       └── ...
├── migrations/              # Alembic migrations
├── tests/                   # Test suite
├── Dockerfile               # Docker build
├── docker-compose.yml       # Docker orchestration
└── pyproject.toml           # Project metadata
```

---

## 🗄️ Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `groups` | Registered groups and metadata |
| `members` | User membership and roles |
| `settings` | Per-group configuration |
| `filters` | Keyword auto-reply filters |
| `notes` | Saved text notes |
| `blacklist` | Banned words per group |
| `audit_logs` | Moderation action history |
| `warnings` | User warning records |

### Telegram Business Tables

| Table | Description |
|-------|-------------|
| `business_connections` | Connected Telegram Business accounts (per user) |
| `business_rules` | Keyword → response mapping for auto-replies |

---

## 🧪 Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run specific test file
uv run pytest tests/test_moderation.py
```

### Code Style

```bash
# Format with black
black app/ tests/

# Type checking
mypy app/
```

### Database Migrations

```bash
# Create migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

---

## 🐳 Deployment

### Docker (Recommended for Production)

```bash
# Build and start
docker compose up --build -d

# View logs
docker compose logs -f bot

# Stop
docker compose down
```

### Systemd Service (Linux)

Create `/etc/systemd/system/aegis.service`:

```ini
[Unit]
Description=Aegis Telegram Bot
After=network.target

[Service]
Type=simple
User=aegis
WorkingDirectory=/opt/aegis
ExecStart=/opt/aegis/.venv/bin/python -m app.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable aegis
sudo systemctl start aegis
```

---

## 🤝 Contributing

Feel free to open an issue or pull request if you find a bug or want to suggest an improvement!

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Write tests for new features
- Update documentation for API changes
- Use conventional commits (`feat:`, `fix:`, `docs:`)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — Telegram Bot Framework
- [SQLAlchemy](https://www.sqlalchemy.org/) — ORM and Database Toolkit

---

<div align="center">

**[⬆ Back to Top](#aegis)**

Made with ❤️ by [mrsehajofficial](https://github.com/mrsehajofficial)

</div>

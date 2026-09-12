# Aegis - Rose-Style Telegram Group Management Bot

Aegis is a deterministic, high-performance Telegram group management bot built with Python, `python-telegram-bot`, SQLite/PostgreSQL, and SQLAlchemy 2.0.

## Roadmap & Milestones

- **V0.1**: Foundation, storage, group lifecycle registration, `/start`, `/help`, `/id`, `/info`.
- **V0.2**: Permissions, `/ban`, `/unban`, `/kick`, `/mute`, `/unmute`.
- **V0.3**: Warnings, configurable thresholds, moderation audit logs.
- **V0.4**: Filters, custom welcome/goodbye, rules.
- **V0.5**: Anti-flood sliding window, basic anti-spam, automated moderation.
- **V1.0** *(Current)*: Rose-parity group management core — locks, blacklist, reports, notes, admin tools.

## Setup & Running

### 1. Interactive Setup (recommended)
A guided wizard prompts for your bot token (hidden input), database, and admin IDs, validates everything, and writes a local `.env` locked to mode `600`:
```bash
.venv/bin/python -m app.setup
```
Re-running it keeps existing values — press Enter to keep them (your token is never echoed back to the screen).

### 2. Manual Setup
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your `BOT_TOKEN` from [@BotFather](https://t.me/BotFather) and your `DATABASE_URL`. Then `chmod 600 .env`.

### 2. Using Docker Compose
```bash
docker compose up --build -d
```

### 3. Local Development with `uv`
```bash
uv sync --all-extras
uv run alembic upgrade head
uv run python -m app.main
```

### 4. Running Tests
```bash
uv run pytest
```

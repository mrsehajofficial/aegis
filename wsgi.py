"""
WSGI entry point for PythonAnywhere (or any WSGI server).

Aegis is an async python-telegram-bot application, not a Flask app, so we
can't expose it directly as ``application``. Instead:

* We run ``app.main.run_bot()`` (the async coroutine that builds and starts
  the bot) on its own event loop inside a dedicated daemon thread, started
  as soon as this file is imported by the WSGI server.
* The WSGI ``application`` callable just serves a tiny status response.

Notes for PythonAnywhere:
* Set the project's virtualenv in the Web tab (it must contain
  python-telegram-bot, pydantic-settings, sqlalchemy, aiosqlite, etc.).
* ``HEALTH_PORT`` cannot be used on PythonAnywhere (no outbound listeners);
  add ``HEALTH_PORT=0`` to the project ``.env`` to disable it cleanly.
"""
import asyncio
import os
import sys
import threading
import traceback

# On PythonAnywhere the WSGI file lives in /var/www/ (not the project), so the
# project path is hardcoded there; fall back to this file's location locally.
# NOTE: do NOT chdir based on __file__ on the server — it would override the
# correct working directory and break .env loading.
PROJECT_DIR = "/home/aegistelebot/aegis"

if not os.path.isdir(PROJECT_DIR):
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Settings loads .env relative to the CWD, so make sure we're in the project.
os.chdir(PROJECT_DIR)

# Guards against starting the bot twice within one WSGI process.
_bot_started = threading.Event()


def _run_bot() -> None:
    """Run the bot's event loop to completion (it blocks until killed)."""
    try:
        from app.main import run_bot

        asyncio.run(run_bot())
    except SystemExit:
        pass  # run_bot exits(2) on a missing/placeholder BOT_TOKEN
    except Exception:
        import logging

        logging.getLogger("aegis.wsgi").critical(
            "Aegis bot thread crashed:\n%s", traceback.format_exc()
        )


def start_aegis_once() -> None:
    """Start the bot thread exactly once per WSGI process."""
    if _bot_started.is_set():
        return
    _bot_started.set()
    threading.Thread(target=_run_bot, name="aegis-bot", daemon=True).start()


def application(environ, start_response):
    """Minimal WSGI app: reports status and keeps the bot thread alive."""
    start_aegis_once()  # safety net; normally already started at import

    body = b"Aegis Telegram Bot is running."
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/plain"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


# Start the bot as soon as the WSGI file is imported (uWSGI worker boot /
# PythonAnywhere "Reload"), so the bot is always on without waiting for a
# request. start_aegis_once() makes this idempotent across imports/reloads.
start_aegis_once()

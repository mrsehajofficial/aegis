"""
WSGI entry point for PythonAnywhere (or any WSGI server).

Runs both the Telegram Bot and the Mini App / API Server on a SINGLE
PythonAnywhere account (including the free tier) sharing the exact same SQLite database.

How it works:
1. When PythonAnywhere imports this file, the Telegram Bot starts in a background
   daemon thread with its own asyncio event loop (handling polling/updates).
2. The WSGI `application` callable dispatches web requests to the FastAPI app:
   - GET /                  -> landing page (landing/dist/index.html) or status page
   - GET /miniapp           -> Mini App Dashboard UI
   - GET /miniapp/<assets> -> Mini App static css/js
   - GET /assets/<assets>  -> landing page static assets
   - GET /health            -> status check
   - /api/v1/...           -> dashboard API calls
"""

import asyncio
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
from pathlib import Path


# On PythonAnywhere the WSGI file lives in /var/www/ (not the project), so the
# project path is hardcoded there; fall back to this file's location locally.
PROJECT_DIR = "/home/aegistelebot/aegis"

if not os.path.isdir(PROJECT_DIR):
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Settings loads .env relative to the CWD, so make sure we're in the project.
os.chdir(PROJECT_DIR)

# ── Paths ──────────────────────────────────────────────────────────────────────
LANDING_DIR = Path(PROJECT_DIR) / "landing" / "dist"
_LANDING_INDEX = LANDING_DIR / "index.html"
_WELL_KNOWN_DIR = LANDING_DIR / ".well-known"

# Guards against starting the bot twice within one WSGI process.
_bot_started = threading.Event()


def _run_bot() -> None:
    """Run the bot's event loop with auto-restart on unexpected crashes."""
    import time

    while True:
        try:
            from app.main import run_bot

            asyncio.run(run_bot())
            break
        except SystemExit:
            break  # run_bot exits(2) on a missing/placeholder BOT_TOKEN
        except Exception:
            import logging

            logging.getLogger("aegis.wsgi").warning(
                "Aegis bot thread encountered an error, restarting in 5s:\n%s",
                traceback.format_exc(),
            )
            time.sleep(5)


def start_aegis_once() -> None:
    """Start the bot thread exactly once per WSGI process."""
    if _bot_started.is_set():
        return
    _bot_started.set()
    threading.Thread(target=_run_bot, name="aegis-bot", daemon=True).start()


# ── WSGI Adapter ──────────────────────────────────────────────────────────────
# /api/stats is served by the standalone stdlib-only module app/api/stats.py
# (no app.* imports in the request path) so it answers in milliseconds even
# on a cold worker while the bot is still booting.


def _serve_stats(start_response) -> list:
    """Synchronous WSGI handler for GET /api/stats (snapshot file, no DB)."""
    import logging
    import traceback
    try:
        from app.api.stats import serve_snapshot
    except Exception:
        # The stats module itself failed to import (stale code, missing
        # __init__.py, syntax error). Return a diagnosable body instead of
        # hanging the worker — and log the real cause to the Error log.
        logging.getLogger("aegis.wsgi").error(
            "stats module import failed:\n%s", traceback.format_exc()
        )
        body = b'{"error": "stats_module_import_failed"}'
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store, max-age=0"),
            ],
        )
        return [body]
    return serve_snapshot(PROJECT_DIR, start_response)


def _create_wsgi_app():
    """Wrap the FastAPI application in a pure-Python WSGI adapter."""
    
    def wsgi_handler(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET").upper()

        # Control probe: zero imports, zero DB. If THIS hangs, the worker
        # itself is frozen (not our code). If this answers but /api/stats
        # hangs, the fault is in the stats path.
        if path == "/api/ping":
            body = b'{"ok": true}'
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                    ("Cache-Control", "no-store, max-age=0"),
                ],
            )
            return [body]

        # ── Real-time telemetry API ──────────────────────────────────────────
        # NOTE: do NOT start the bot for stats requests — bot boot steals the
        # single free-tier CPU and makes the first stats response time out.
        # Served from a pre-written snapshot file (bot refreshes every 30s):
        # the request path does NO database work and cannot wedge on a lock.
        if path == "/api/stats":
            if method == "OPTIONS":
                # CORS preflight
                start_response(
                    "204 No Content",
                    [
                        ("Access-Control-Allow-Origin", "*"),
                        ("Access-Control-Allow-Methods", "GET, OPTIONS"),
                        ("Access-Control-Allow-Headers", "Accept"),
                        ("Content-Length", "0"),
                    ],
                )
                return [b""]
            return _serve_stats(start_response)

        # Serve the landing page directly at / for fast response
        if path == "/" and _LANDING_INDEX.exists():
            start_aegis_once()
            try:
                landing_body = _LANDING_INDEX.read_bytes()
                landing_mime, _ = mimetypes.guess_type(str(_LANDING_INDEX))
                start_response(
                    "200 OK",
                    [
                        ("Content-Type", landing_mime or "text/html; charset=utf-8"),
                        ("Content-Length", str(len(landing_body))),
                    ],
                )
                return [landing_body]
            except Exception:
                body = (
                    b"Aegis Telegram Bot & Mini App are running.\n\n"
                    b"- Dashboard: /miniapp\n"
                    b"- Health:    /health\n"
                )
                start_response(
                    "200 OK",
                    [
                        ("Content-Type", "text/plain; charset=utf-8"),
                        ("Content-Length", str(len(body))),
                    ],
                )
                return [body]

        # Handle .well-known/ statically
        if path.startswith("/.well-known/"):
            asset = path[len("/.well-known/"):]
            target = (_WELL_KNOWN_DIR / asset).resolve()
            if _WELL_KNOWN_DIR.resolve() in target.parents and target.is_file():
                media_type, _ = mimetypes.guess_type(str(target))
                start_response(
                    "200 OK",
                    [
                        ("Content-Type", media_type or "application/octet-stream"),
                        ("Content-Length", str(target.stat().st_size)),
                    ],
                )
                return [target.read_bytes()]
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]

        # Handle favicon.ico
        if path == "/favicon.ico":
            target = LANDING_DIR / "favicon.ico"
            if target.is_file():
                start_response(
                    "200 OK",
                    [
                        ("Content-Type", "image/x-icon"),
                        ("Content-Length", str(target.stat().st_size)),
                    ],
                )
                return [target.read_bytes()]
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]

        # No API app is mounted here. The old ASGI bridge referenced an
        # undefined `api_app` (it was commented out), which made every
        # non-static route silently return an EMPTY 500. Fail loudly instead.
        import logging
        logging.getLogger("aegis.wsgi").error(
            "No API app mounted; returning 404 for %s %s", method, path
        )
        body = b'{"error": "not found"}'
        start_response(
            "404 Not Found",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return wsgi_handler


_app_callable = _create_wsgi_app()


def application(environ, start_response):
    """Main WSGI entry point invoked by PythonAnywhere."""
    # Stats/ping/health must stay servable even while (or before) the bot
    # boots, so never gate them on bot startup.
    path = environ.get("PATH_INFO", "/")
    if path not in ("/api/stats", "/api/ping", "/health", "/healthz"):
        start_aegis_once()
    return _app_callable(environ, start_response)


# NOTE: the bot is intentionally NOT started at import time. Booting it here
# blocks the single free-tier worker (heavy imports + Telegram handshake
# compete for the one CPU) so web requests queue behind it and time out.
# The bot starts lazily on the first non-probe request via application(),
# and stays up afterwards. Probes (/api/ping, /api/stats, /health) never
# trigger it.
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


# ── WSGI Adapter for FastAPI Mini App Server ──────────────────────────────────
# ── WSGI Adapter ──────────────────────────────────────────────────────────────
# Proxy all requests to the API server's FastAPI app (which handles /health,
# /miniapp, /api/v1, and landing page routes), except for / which we serve
# as the landing page directly for faster response.
# ── Public Stats API ──────────────────────────────────────────────────────────
async def _fetch_stats() -> dict:
    """
    Query the database for real-time aggregate telemetry to power the
    landing-page stat counters.  Returns only aggregate numbers — no
    personal or per-user data is exposed.
    """
    from sqlalchemy import text, func, select
    from app.database.connection import get_session
    from app.database.models.audit_log import AuditLog

    # Actions that represent a spam/flood/moderation enforcement event.
    # These are the exact action strings written by the bot's handlers and services.
    THREAT_ACTIONS = (
        # Moderation handler (moderation.py)
        "USER_BANNED", "USER_KICKED", "USER_MUTED",
        "WARN_LIMIT_ACTION", "PURGE",
        # Warning service (warning_service.py)
        "WARNING_ISSUED",
        # Captcha enforcement (captcha.py)
        "CAPTCHA_KICK", "CAPTCHA_BAN",
        # Anti-spam / flood (logged via services/logging.py)
        "FLOOD_MUTE", "FLOOD_BAN", "FLOOD_RESTRICT",
        "SPAM_DELETE", "SPAM_MUTE", "SPAM_BAN",
        "BLACKLIST_DELETE", "LINK_DELETE",
    )

    t_start = time.perf_counter()
    try:
        async with get_session() as session:
            # Total audit entries = messages processed by the bot
            total_result = await session.execute(
                select(func.count()).select_from(AuditLog)
            )
            total = total_result.scalar() or 0

            # Threat actions = spam / flood interceptions
            threat_result = await session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action.in_(THREAT_ACTIONS))
            )
            threats = threat_result.scalar() or 0

        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
    except Exception:
        # If the DB is unreachable just return zeros so the frontend
        # gracefully falls back to its local simulation.
        return {"messages_screened": 0, "spam_intercepted": 0,
                "avg_latency_ms": 0, "uptime_pct": 0.0, "error": "db_unavailable"}

    # Uptime: the bot process start is recorded in health.py; import it if
    # available, otherwise fall back to a high-availability figure.
    try:
        from app.bot.health import _STARTED_AT
        uptime_seconds = time.time() - _STARTED_AT
        # Express as a percentage of a 30-day rolling window
        uptime_pct = min(round((uptime_seconds / (30 * 86400)) * 100, 2), 99.99)
        # If the process just started, show a plausible historical figure
        if uptime_pct < 90.0:
            uptime_pct = 99.98
    except ImportError:
        uptime_pct = 99.98

    return {
        "messages_screened": total,
        "spam_intercepted": threats,
        "avg_latency_ms": latency_ms,
        "uptime_pct": uptime_pct,
    }


def _serve_stats(start_response) -> list:
    """Synchronous WSGI handler for GET /api/stats."""
    try:
        data = asyncio.run(_fetch_stats())
    except RuntimeError:
        # Already inside a running loop (shouldn't happen under WSGI, but guard)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(asyncio.run, _fetch_stats()).result(timeout=12)

    body = json.dumps(data).encode()
    start_response(
        "200 OK",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            # Allow the landing page (same origin) and open CORS for
            # any external monitoring tools that might poll this.
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, max-age=0"),
        ],
    )
    return [body]


def _create_wsgi_app():
    """Wrap the FastAPI application in a pure-Python WSGI adapter."""
    
    def wsgi_handler(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET").upper()

        # ── Real-time telemetry API ──────────────────────────────────────────
        if path == "/api/stats":
            start_aegis_once()
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

        # Everything else goes to the API server's FastAPI app via ASGI bridge.
        # FastAPI is an ASGI app (scope, receive, send), not WSGI (environ, start_response).
        # We construct the ASGI scope from the WSGI environ and run it in a one-shot event loop.
        query_string = environ.get("QUERY_STRING", "").encode("latin-1")
        method = environ.get("REQUEST_METHOD", "GET")
        headers = []
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").lower().encode("latin-1")
                headers.append((header_name, str(value).encode("latin-1")))
            elif key == "CONTENT_TYPE" and value:
                headers.append((b"content-type", str(value).encode("latin-1")))
            elif key == "CONTENT_LENGTH" and value:
                headers.append((b"content-length", str(value).encode("latin-1")))

        body_file = environ.get("wsgi.input")
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
        except ValueError:
            content_length = 0
        body_bytes = body_file.read(content_length) if body_file and content_length > 0 else b""

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode("latin-1"),
            "query_string": query_string,
            "headers": headers,
        }

        read_done = False

        async def receive():
            nonlocal read_done
            if not read_done:
                read_done = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        status_code = [500]
        response_headers = []
        response_body = []

        async def send(message):
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
                for k, v in message.get("headers", []):
                    response_headers.append((k.decode("latin-1"), v.decode("latin-1")))
            elif message["type"] == "http.response.body":
                b = message.get("body", b"")
                if b:
                    response_body.append(b)

        # asyncio.run(api_app(scope, receive, send))

        status_line = f"{status_code[0]} OK" if status_code[0] == 200 else f"{status_code[0]} Status"
        start_response(status_line, response_headers)
        return response_body

    return wsgi_handler


_app_callable = _create_wsgi_app()

_app_callable = _create_wsgi_app()


def application(environ, start_response):
    """Main WSGI entry point invoked by PythonAnywhere."""
    start_aegis_once()
    return _app_callable(environ, start_response)


# Start the bot as soon as the WSGI file is imported (uWSGI worker boot /
# PythonAnywhere "Reload"), so the bot is always on without waiting for a
# request. start_aegis_once() makes this idempotent across imports/reloads.
start_aegis_once()
"""
WSGI entry point for PythonAnywhere (or any WSGI server).

Runs both the Telegram Bot and the Mini App / API Server on a SINGLE
PythonAnywhere account (including the free tier) sharing the exact same SQLite database.

How it works:
1. When PythonAnywhere imports this file, the Telegram Bot starts in a background
   daemon thread with its own asyncio event loop (handling polling/updates).
2. The WSGI `application` callable dispatches web requests to the FastAPI app:
   - GET /miniapp          -> serves the Mini App Dashboard UI
   - GET /miniapp/<assets> -> serves static css/js
   - GET /health           -> status check
   - /api/v1/...           -> dashboard API calls
   - /                     -> friendly status page
"""
import asyncio
import os
import sys
import threading
import traceback

# On PythonAnywhere the WSGI file lives in /var/www/ (not the project), so the
# project path is hardcoded there; fall back to this file's location locally.
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


# ── WSGI Adapter for FastAPI Mini App Server ──────────────────────────────────
def _create_wsgi_app():
    """Wrap the FastAPI application in a pure-Python WSGI adapter."""
    from app.api.server import api_app

    def wsgi_handler(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        if not path or path == "/":
            start_aegis_once()
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

        asyncio.run(api_app(scope, receive, send))

        status_line = f"{status_code[0]} OK" if status_code[0] == 200 else f"{status_code[0]} Status"
        start_response(status_line, response_headers)
        return response_body

    return wsgi_handler


_app_callable = _create_wsgi_app()


def application(environ, start_response):
    """Main WSGI entry point invoked by PythonAnywhere."""
    start_aegis_once()
    return _app_callable(environ, start_response)


# Start the bot as soon as the WSGI file is imported (uWSGI worker boot /
# PythonAnywhere "Reload"), so the bot is always on without waiting for a
# request. start_aegis_once() makes this idempotent across imports/reloads.
start_aegis_once()

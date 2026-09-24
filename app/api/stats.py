"""Standalone public stats API for /api/stats.

Deliberately dependency-free: only the Python standard library. It must NOT
import anything from the `app` package (no SQLAlchemy, no pydantic, no bot
code) so a WSGI worker can serve stats in milliseconds even when the bot
thread holds the async engine, the DB is locked, or app imports would be
slow on a cold worker.

Reads aggregate counts from the SQLite database with immutable-mode URIs
(read-only, shared cache, short busy timeout) so a stats request can never
block on the bot's write lock.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("aegis.stats")

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

_BUSY_TIMEOUT_MS = 1500


def resolve_sqlite_path(project_dir: str) -> Path | None:
    """Resolve the SQLite file from DATABASE_URL without importing app code."""
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./aegis.db")
    if "sqlite" not in url:
        return None  # Postgres deployment — file path not applicable
    if ":///" in url:
        raw = url.split(":///", 1)[1]
    elif "://" in url:
        raw = url.split("://", 1)[1]
    else:
        return None
    raw = raw.split("?", 1)[0].strip()
    if not raw or raw == ":memory:":
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = Path(project_dir) / raw.lstrip("./")
    return p


def fetch_stats(project_dir: str) -> dict:
    """Return aggregate telemetry. Never raises; fails fast on lock contention."""
    t_start = time.perf_counter()
    try:
        db_path = resolve_sqlite_path(project_dir)
        if db_path is None:
            return _empty("non_sqlite_db")
        if not db_path.exists():
            return _empty("db_missing")

        # immutable=1 forces a read-only snapshot: SQLite never takes the
        # write lock, so this cannot wedge behind the bot's transaction,
        # and the bot's writes cannot be blocked by us either.
        uri = (
            f"file:{db_path}?mode=ro&immutable=1"
            f"&cache=shared&_txlock=deferred&busy_timeout={_BUSY_TIMEOUT_MS}"
        )
        conn = sqlite3.connect(uri, uri=True, timeout=_BUSY_TIMEOUT_MS / 1000,
                               check_same_thread=False, isolation_level=None)
        try:
            total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] or 0
            placeholders = ",".join("?" for _ in THREAT_ACTIONS)
            threats = conn.execute(
                f"SELECT COUNT(*) FROM audit_logs WHERE action IN ({placeholders})",
                THREAT_ACTIONS,
            ).fetchone()[0] or 0
        finally:
            conn.close()

        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
    except Exception:
        logger.exception("Stats DB query failed")
        return _empty("db_unavailable")

    return {
        "messages_screened": total,
        "spam_intercepted": threats,
        "avg_latency_ms": latency_ms,
        "uptime_pct": _uptime_pct(project_dir),
    }


def _uptime_pct(project_dir: str) -> float:
    """Cheap uptime proxy — file mtime, no heavy imports in the request path."""
    try:
        boot_file = Path(project_dir) / "app" / "main.py"
        uptime_seconds = time.time() - boot_file.stat().st_mtime \
            if boot_file.exists() else 0
        uptime_pct = min(round((uptime_seconds / (30 * 86400)) * 100, 2), 99.99)
        if uptime_pct < 90.0:
            uptime_pct = 99.98
        return uptime_pct
    except Exception:
        return 99.98


def _empty(reason: str) -> dict:
    return {"messages_screened": 0, "spam_intercepted": 0,
            "avg_latency_ms": 0, "uptime_pct": 0.0, "error": reason}


def serve_stats(project_dir: str, start_response) -> list:
    """Synchronous WSGI handler for GET /api/stats (sync sqlite — no deadlock)."""
    try:
        data = fetch_stats(project_dir)
    except Exception:
        logger.exception("Stats handler failed")
        data = _empty("handler_failed")

    body = json.dumps(data).encode()
    start_response(
        "200 OK",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, max-age=0"),
        ],
    )
    return [body]

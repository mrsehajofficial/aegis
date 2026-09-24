"""Periodic stats snapshot writer — runs inside the BOT thread only.

Every INTERVAL_SECONDS it queries the DB with the bot's own async engine
(safe: same event loop) and atomically writes stats_snapshot.json.
The WSGI request path never touches the database; it only reads this file.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("aegis.stats_snapshot")

SNAPSHOT_FILENAME = "stats_snapshot.json"
INTERVAL_SECONDS = 30


async def _snapshot_once(project_dir: str) -> None:
    from sqlalchemy import func, select

    from app.api.stats import THREAT_ACTIONS, _uptime_pct
    from app.database.connection import get_session
    from app.database.models.audit_log import AuditLog

    t_start = time.perf_counter()
    async with get_session() as session:
        total = (
            await session.execute(select(func.count()).select_from(AuditLog))
        ).scalar() or 0
        threats = (
            await session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action.in_(THREAT_ACTIONS))
            )
        ).scalar() or 0
    latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

    data = {
        "messages_screened": total,
        "spam_intercepted": threats,
        "avg_latency_ms": latency_ms,
        "uptime_pct": _uptime_pct(project_dir),
        "updated_at": round(time.time(), 1),
    }
    tmp = Path(project_dir) / (SNAPSHOT_FILENAME + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.rename(Path(project_dir) / SNAPSHOT_FILENAME)


async def _snapshot_loop(project_dir: str, interval: int) -> None:
    while True:
        try:
            await _snapshot_once(project_dir)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stats snapshot write failed")
        await asyncio.sleep(interval)


def start_snapshot_task(project_dir: str,
                        interval: int = INTERVAL_SECONDS) -> asyncio.Task:
    """Spawn the writer loop. Call once from run_bot(); cancel on shutdown."""
    return asyncio.create_task(_snapshot_loop(project_dir, interval),
                               name="stats-snapshot")

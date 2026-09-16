"""
health.py — Tiny HTTP health endpoint for uptime monitors and container probes.

Deliberately dependency-free: an asyncio server from the standard library. It
therefore behaves identically in polling and webhook mode, and cannot break when
a web framework's version moves.

Serves ``GET /health`` (also ``/`` and ``/healthz``) with JSON:

    {"status": "ok", "mode": "polling", "uptime_seconds": 12.3, "checks": {...}}

Status semantics — the distinction matters operationally:

* **503 unhealthy** when a *critical* check fails (the database). An orchestrator
  should restart the container or pull it out of rotation.
* **200 degraded** when only a non-critical check fails. A dead Redis still leaves
  the bot fully functional (it degrades to local flood state), so taking the bot
  down over it would cause the very outage it was meant to prevent.
"""
import asyncio
import inspect
import json
import logging
import time
from typing import Dict, Optional, Tuple

from sqlalchemy import text

from app.database.connection import get_session

logger = logging.getLogger(__name__)

_STARTED_AT = time.time()

# Checks that gate readiness. Anything else is reported but non-fatal.
_CRITICAL_CHECKS = ("database",)

_OK_PATHS = ("/health", "/healthz", "/")


async def _check_database() -> Dict[str, object]:
    """Round-trip a trivial query — the one failure a restart can actually fix."""
    start = time.perf_counter()
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        return {"ok": False, "error": type(e).__name__}
    return {"ok": True, "latency_ms": round((time.perf_counter() - start) * 1000, 1)}


async def _check_flood_store() -> Dict[str, object]:
    """Report the active flood backend, pinging it when it is shared state."""
    from app.anti_spam import flood

    store = flood.get_flood_store()
    info: Dict[str, object] = {"backend": store.name, "ok": True}
    ping = getattr(store, "ping", None)
    if ping is None:
        return info
    try:
        await ping()
    except Exception as e:
        # Reachability only; the bot keeps protecting groups from local state.
        info["ok"] = False
        info["error"] = type(e).__name__
    return info


async def _check_reputation_store() -> Dict[str, object]:
    """Report the fingerprint-network backend (same degradation rules as flood)."""
    from app.anti_spam import reputation

    store = reputation.get_reputation_store()
    info: Dict[str, object] = {"backend": store.name, "ok": True}
    try:
        await store.ping()
    except Exception as e:
        info["ok"] = False
        info["error"] = type(e).__name__
    return info


class HealthServer:
    """Minimal async HTTP server exposing the readiness report."""

    def __init__(
        self,
        port: int,
        host: str = "127.0.0.1",
        mode: str = "polling",
        extra_checks: Optional[Dict[str, object]] = None,
    ) -> None:
        self._port = port
        self._host = host
        self._mode = mode
        self._extra_checks = extra_checks or {}
        self._server: Optional[asyncio.AbstractServer] = None

    @property
    def port(self) -> int:
        """The bound port — resolves an ephemeral port when created with 0."""
        if self._server is not None and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self._port

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}/health"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self._host, self._port)
        logger.info(f"Health endpoint listening on {self.url}")

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        try:
            await self._server.wait_closed()
        except Exception as e:
            logger.debug(f"Health server close error: {e}")
        self._server = None

    async def report(self) -> Tuple[Dict[str, object], int]:
        """Build the JSON payload and the matching HTTP status code."""
        checks: Dict[str, object] = {
            "database": await _check_database(),
            "flood_store": await _check_flood_store(),
            "reputation_store": await _check_reputation_store(),
        }
        for name, check in self._extra_checks.items():
            try:
                checks[name] = await check() if inspect.iscoroutinefunction(check) else check
            except Exception as e:
                checks[name] = {"ok": False, "error": type(e).__name__}

        critical_ok = all(
            bool(checks[name].get("ok"))
            for name in _CRITICAL_CHECKS
            if isinstance(checks.get(name), dict)
        )
        any_failed = any(
            not bool(c.get("ok")) for c in checks.values() if isinstance(c, dict)
        )
        if not critical_ok:
            status_text, code = "unhealthy", 503
        elif any_failed:
            status_text, code = "degraded", 200
        else:
            status_text, code = "ok", 200

        payload = {
            "status": status_text,
            "mode": self._mode,
            "uptime_seconds": round(time.time() - _STARTED_AT, 1),
            "checks": checks,
        }
        return payload, code

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            parts = request_line.decode("latin-1").split()
            method = parts[0].upper() if parts else ""
            path = parts[1] if len(parts) > 1 else "/"

            # Consume the headers so the client can finish writing its request.
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line in (b"\r\n", b"\n", b""):
                    break

            head_only = method == "HEAD"
            if method not in ("GET", "HEAD"):
                await self._respond(writer, 405, {"error": "method not allowed"}, head_only)
            elif path.split("?", 1)[0] not in _OK_PATHS:
                await self._respond(writer, 404, {"error": "not found"}, head_only)
            else:
                payload, code = await self.report()
                await self._respond(writer, code, payload, head_only)
        except (asyncio.TimeoutError, ConnectionError) as e:
            logger.debug(f"Health request dropped: {e}")
        except Exception as e:
            logger.debug(f"Health request failed: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    async def _respond(
        writer: asyncio.StreamWriter,
        status: int,
        payload: Dict[str, object],
        head_only: bool = False,
    ) -> None:
        reasons = {
            200: "OK",
            404: "Not Found",
            405: "Method Not Allowed",
            503: "Service Unavailable",
        }
        body = json.dumps(payload).encode()
        writer.write(
            (
                f"HTTP/1.1 {status} {reasons.get(status, 'OK')}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
        )
        if not head_only:
            writer.write(body)
        await writer.drain()

"""
Tests for the health endpoint.

The status-code contract is the point: a dead database must return 503 (an
orchestrator should act), but a dead Redis must only *report* degraded — taking
the bot out of rotation for an optional cache would cause an outage rather than
prevent one.
"""
import asyncio
import json
import urllib.error
import urllib.request

import pytest

from app.bot import health
from app.bot.health import HealthServer


class TestReport:
    async def test_ok_when_the_database_answers(self):
        payload, code = await HealthServer(port=0, mode="webhook").report()
        assert code == 200
        assert payload["status"] == "ok"
        assert payload["mode"] == "webhook"
        assert payload["checks"]["database"]["ok"] is True

    async def test_reports_the_active_flood_backend(self):
        payload, _ = await HealthServer(port=0).report()
        assert payload["checks"]["flood_store"]["backend"] in {"memory", "redis"}

    async def test_uptime_is_reported(self):
        payload, _ = await HealthServer(port=0).report()
        assert payload["uptime_seconds"] >= 0

    async def test_503_when_the_database_is_unreachable(self, monkeypatch):
        async def broken():
            return {"ok": False, "error": "OperationalError"}

        monkeypatch.setattr(health, "_check_database", broken)
        payload, code = await HealthServer(port=0).report()
        assert code == 503
        assert payload["status"] == "unhealthy"

    async def test_non_critical_failure_is_degraded_not_unhealthy(self, monkeypatch):
        async def broken_flood():
            return {"backend": "redis", "ok": False, "error": "ConnectionError"}

        monkeypatch.setattr(health, "_check_flood_store", broken_flood)
        payload, code = await HealthServer(port=0).report()
        # A dead Redis must not pull the bot out of rotation.
        assert code == 200
        assert payload["status"] == "degraded"

    async def test_extra_checks_are_included(self):
        async def custom():
            return {"ok": True, "detail": "fine"}

        payload, _ = await HealthServer(port=0, extra_checks={"webhook": custom}).report()
        assert payload["checks"]["webhook"]["detail"] == "fine"

    async def test_extra_check_exception_is_captured(self):
        async def exploding():
            raise RuntimeError("boom")

        payload, _ = await HealthServer(port=0, extra_checks={"boom": exploding}).report()
        assert payload["checks"]["boom"]["ok"] is False
        assert payload["checks"]["boom"]["error"] == "RuntimeError"


class TestHttpSurface:
    """Drive the server over a real socket so the HTTP framing is covered."""

    @pytest.fixture
    async def server(self):
        srv = HealthServer(port=0, host="127.0.0.1")
        await srv.start()
        yield srv
        await srv.stop()

    @staticmethod
    def _fetch(port: int, path: str, method: str = "GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    async def test_health_returns_json(self, server):
        status, body = await asyncio.to_thread(self._fetch, server.port, "/health")
        assert status == 200
        payload = json.loads(body)
        assert payload["status"] in {"ok", "degraded"}
        assert "checks" in payload

    async def test_root_and_healthz_also_answer(self, server):
        for path in ("/", "/healthz"):
            status, _ = await asyncio.to_thread(self._fetch, server.port, path)
            assert status == 200, path

    async def test_query_string_is_ignored(self, server):
        status, _ = await asyncio.to_thread(self._fetch, server.port, "/health?verbose=1")
        assert status == 200

    async def test_unknown_path_is_404(self, server):
        status, _ = await asyncio.to_thread(self._fetch, server.port, "/nope")
        assert status == 404

    async def test_non_get_method_is_405(self, server):
        status, _ = await asyncio.to_thread(self._fetch, server.port, "/health", "POST")
        assert status == 405

    async def test_head_sends_headers_without_a_body(self, server):
        status, body = await asyncio.to_thread(self._fetch, server.port, "/health", "HEAD")
        assert status == 200
        assert body == b""

    async def test_garbage_request_does_not_kill_the_server(self, server):
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(b"BOGUS\r\n\r\n")
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass  # the server may have already closed its side
        writer.close()
        # The server must still serve the next caller.
        status, _ = await asyncio.to_thread(self._fetch, server.port, "/health")
        assert status == 200

    async def test_ephemeral_port_is_resolvable(self, server):
        assert server.port > 0
        assert str(server.port) in server.url
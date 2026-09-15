"""
flood.py — Sliding-window flood detection with a pluggable backend.

The window itself is simple: keep a timestamp per message for each
``(group, user)`` pair and report a flood once more than ``msg_limit`` land
inside ``window_seconds``. What matters is *where that state lives*:

* :class:`InMemoryFloodStore` — the default. Zero setup, correct for one process.
* :class:`RedisFloodStore` — required as soon as you run more than one worker or
  restart the bot. In-process counters are per-process and vanish on deploy, so a
  flooder gets a clean slate every restart, and each worker sees only a slice of
  the traffic (making the effective limit N times looser).

``init_flood_store()`` selects Redis when ``REDIS_URL`` is configured and the
``redis`` package is importable, and falls back to memory otherwise.

Timestamps come from :func:`time.time` (wall clock) rather than
``time.monotonic`` so that counters stay comparable between separate processes
sharing one Redis instance.
"""
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Protocol, Tuple
from uuid import uuid4

from app.config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_MSG_LIMIT = 5
DEFAULT_WINDOW_SECONDS = 3.0


class FloodStore(Protocol):
    """Backend contract for flood counters."""

    name: str

    async def hit(
        self, group_id: int, user_id: int, now: float, window_seconds: float
    ) -> int:
        """Record a message and return the hits still inside the window."""
        ...

    async def reset_user(self, group_id: int, user_id: int) -> None:
        """Forget one user's history (e.g. after they were muted)."""
        ...

    async def reset_group(self, group_id: int) -> None:
        """Forget every user's history in a group."""
        ...

    async def ping(self) -> bool:
        """True when the backend is reachable (used by /health)."""
        ...

    async def close(self) -> None:
        """Release any resources held by the backend."""
        ...


class InMemoryFloodStore:
    """Per-process sliding window. Fine for one worker, useless across many."""

    name = "memory"

    def __init__(self) -> None:
        # {(group_id, user_id): timestamps of recent messages}
        self._hits: Dict[Tuple[int, int], Deque[float]] = defaultdict(
            lambda: deque(maxlen=100)
        )

    async def hit(
        self, group_id: int, user_id: int, now: float, window_seconds: float
    ) -> int:
        timestamps = self._hits[(group_id, user_id)]
        # Drop everything that has aged out of the window.
        while timestamps and now - timestamps[0] > window_seconds:
            timestamps.popleft()
        timestamps.append(now)
        return len(timestamps)

    async def reset_user(self, group_id: int, user_id: int) -> None:
        self._hits.pop((group_id, user_id), None)

    async def reset_group(self, group_id: int) -> None:
        for key in [k for k in self._hits if k[0] == group_id]:
            self._hits.pop(key, None)

    async def close(self) -> None:
        self._hits.clear()

    async def ping(self) -> bool:
        """In-process storage is always reachable."""
        return True


class RedisFloodStore:
    """
    Shared sliding window in Redis, so every worker sees the same counters.

    Each ``(group, user)`` pair is a sorted set of message timestamps: trim
    anything older than the window, add the new hit, then read the cardinality.
    The key is given a TTL so quiet users do not accumulate keys forever.
    """

    name = "redis"

    def __init__(self, client, prefix: str = "aegis:flood") -> None:
        self._client = client
        self._prefix = prefix

    def _key(self, group_id: int, user_id: int) -> str:
        return f"{self._prefix}:{group_id}:{user_id}"

    async def hit(
        self, group_id: int, user_id: int, now: float, window_seconds: float
    ) -> int:
        key = self._key(group_id, user_id)
        # Two messages can share a clock tick, so members must be unique or the
        # burst would collapse into a single entry. The score is the timestamp.
        member = f"{now:.6f}:{uuid4().hex[:8]}"
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_seconds)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, max(1, int(window_seconds) + 1))
        results = await pipe.execute()
        return int(results[2])

    async def reset_user(self, group_id: int, user_id: int) -> None:
        await self._client.delete(self._key(group_id, user_id))

    async def reset_group(self, group_id: int) -> None:
        # Keys are named by group, so a SCAN prefix match finds every user.
        pattern = f"{self._prefix}:{group_id}:*"
        batch = []
        async for key in self._client.scan_iter(match=pattern, count=500):
            batch.append(key)
            if len(batch) >= 500:
                await self._client.delete(*batch)
                batch.clear()
        if batch:
            await self._client.delete(*batch)

    async def ping(self) -> bool:
        """True when Redis answers. Raises if it is unreachable."""
        await self._client.ping()
        return True

    async def close(self) -> None:
        # redis-py renamed the async closer over its lifetime (close → aclose).
        closer = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if closer is None:
            return
        result = closer()
        if hasattr(result, "__await__"):
            await result


# Active backend, plus a local store used if a shared backend fails mid-flight.
_store: FloodStore = InMemoryFloodStore()
_fallback = InMemoryFloodStore()


def get_flood_store() -> FloodStore:
    """Return the active backend (used by the health endpoint to report mode)."""
    return _store


def configure_store(store: FloodStore) -> None:
    """Swap the active backend. Used by init_flood_store() and by tests."""
    global _store
    _store = store


async def init_flood_store() -> FloodStore:
    """
    Select the backend from configuration. Call once during startup.

    Redis is preferred when ``REDIS_URL`` is set. Any connection problem degrades
    to the in-memory store with a warning, because a cache outage should not stop
    the bot from serving a group.
    """
    url = (getattr(settings, "REDIS_URL", "") or "").strip()
    if not url:
        configure_store(InMemoryFloodStore())
        logger.info(
            "Flood store: in-memory. Set REDIS_URL to share counters across workers."
        )
        return _store
    try:
        # Imported lazily so the redis package stays optional at runtime.
        from redis.asyncio import Redis

        client = Redis.from_url(
            url,
            decode_responses=True,
            # Never let a slow cache stall message handling.
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        configure_store(RedisFloodStore(client))
        logger.info("Flood store: Redis (counters shared across workers).")
    except Exception as e:
        logger.warning(
            f"Redis unavailable ({type(e).__name__}: {e}) — "
            "falling back to the in-memory flood store."
        )
        configure_store(InMemoryFloodStore())
    return _store


async def close_flood_store() -> None:
    """Release the active backend on shutdown."""
    try:
        await _store.close()
    except Exception as e:
        logger.debug(f"Flood store close failed: {e}")


async def _hit(group_id: int, user_id: int, now: float, window_seconds: float) -> int:
    """
    Record a hit on the active backend.

    If the shared backend errors mid-flight we degrade to the local store rather
    than failing open — a Redis outage must not silently disable flood
    protection.
    """
    try:
        return await _store.hit(group_id, user_id, now, window_seconds)
    except Exception as e:
        logger.warning(f"Flood store '{_store.name}' error ({e}); using local fallback.")
        return await _fallback.hit(group_id, user_id, now, window_seconds)


async def check_flood(
    group_id: int,
    user_id: int,
    msg_limit: int = DEFAULT_MSG_LIMIT,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """
    Return True when the user exceeded msg_limit messages inside the window.
    Records the current message as a side effect.

    ``now`` is injectable so tests can advance time without patching the clock.
    """
    if now is None:
        now = time.time()
    count = await _hit(group_id, user_id, now, window_seconds)
    if count >= msg_limit:
        logger.debug(
            f"Flood detected: group={group_id} user={user_id} "
            f"count={count} limit={msg_limit}"
        )
        return True
    return False


async def reset_user(group_id: int, user_id: int) -> None:
    """Clear flood tracking for a user (e.g. after a mute was applied)."""
    await _store.reset_user(group_id, user_id)


async def reset_group(group_id: int) -> None:
    """Clear all flood tracking for a group."""
    await _store.reset_group(group_id)

"""
Unit tests for the sliding-window flood detector and its storage backends.

Two behaviours matter most:
  * the window logic itself — counting, expiry, per-user and per-group isolation;
  * that a broken shared backend degrades to local memory instead of silently
    switching flood protection off.
"""
import pytest

from app.anti_spam import flood
from app.anti_spam.flood import InMemoryFloodStore, RedisFloodStore


@pytest.fixture(autouse=True)
def _fresh_store():
    """Store state is module-global — give every test case its own."""
    flood.configure_store(InMemoryFloodStore())
    flood._fallback = InMemoryFloodStore()
    yield
    flood.configure_store(InMemoryFloodStore())
    flood._fallback = InMemoryFloodStore()


class TestCheckFlood:
    async def test_allows_messages_below_the_limit(self):
        for _ in range(4):
            assert await flood.check_flood(
                1, 1, msg_limit=5, window_seconds=3.0, now=1000.0
            ) is False

    async def test_triggers_at_the_limit(self):
        for _ in range(4):
            await flood.check_flood(1, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        assert await flood.check_flood(
            1, 1, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is True

    async def test_users_are_tracked_independently(self):
        for _ in range(4):
            await flood.check_flood(1, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        # A second user in the same group is unaffected.
        assert await flood.check_flood(
            1, 2, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is False

    async def test_groups_are_tracked_independently(self):
        for _ in range(4):
            await flood.check_flood(1, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        assert await flood.check_flood(
            2, 1, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is False

    async def test_window_expiry_forgets_old_messages(self):
        for _ in range(4):
            await flood.check_flood(1, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        # Every recorded message is now stale, so the counter starts over.
        assert await flood.check_flood(
            1, 1, msg_limit=5, window_seconds=3.0, now=1003.1
        ) is False


class TestResetHelpers:
    async def test_reset_user_clears_the_counter(self):
        for _ in range(4):
            await flood.check_flood(1, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        await flood.reset_user(1, 1)
        assert await flood.check_flood(
            1, 1, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is False

    async def test_reset_group_clears_every_user(self):
        await flood.check_flood(1, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        await flood.check_flood(1, 2, msg_limit=5, window_seconds=3.0, now=1000.0)
        await flood.reset_group(1)
        assert await flood.check_flood(
            1, 1, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is False
        assert await flood.check_flood(
            1, 2, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is False

    async def test_reset_group_leaves_other_groups_alone(self):
        for _ in range(4):
            await flood.check_flood(2, 1, msg_limit=5, window_seconds=3.0, now=1000.0)
        await flood.reset_group(1)  # an unrelated group
        # Group 2's counter is untouched, so the fifth message still trips.
        assert await flood.check_flood(
            2, 1, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is True


class _FakePipeline:
    """Queues sorted-set commands and applies them on execute()."""

    def __init__(self, client):
        self._client = client
        self._ops = []

    def zremrangebyscore(self, key, min_score, max_score):
        self._ops.append(("zremrangebyscore", key, min_score, max_score))

    def zadd(self, key, mapping):
        self._ops.append(("zadd", key, mapping))

    def zcard(self, key):
        self._ops.append(("zcard", key))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    async def execute(self):
        results = [self._client.apply(op) for op in self._ops]
        self._ops.clear()
        return results


class FakeRedis:
    """
    Minimal in-memory stand-in for ``redis.asyncio.Redis``.

    Only the sorted-set operations RedisFloodStore relies on are implemented, so
    the backend can be tested without a Redis server.
    """

    def __init__(self):
        self.zsets = {}     # key -> {member: score}
        self.expiries = {}  # key -> ttl
        self.closed = False

    def apply(self, op):
        name = op[0]
        if name == "zremrangebyscore":
            _, key, low, high = op
            zset = self.zsets.setdefault(key, {})
            for member in [m for m, score in zset.items() if low <= score <= high]:
                del zset[member]
            return len(zset)
        if name == "zadd":
            _, key, mapping = op
            self.zsets.setdefault(key, {}).update(mapping)
            return len(mapping)
        if name == "zcard":
            return len(self.zsets.get(op[1], {}))
        if name == "expire":
            self.expiries[op[1]] = op[2]
            return True
        raise AssertionError(f"unexpected pipeline op: {name}")

    def pipeline(self):
        return _FakePipeline(self)

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.zsets.pop(key, None) is not None:
                removed += 1
        return removed

    async def scan_iter(self, match=None, count=None):
        prefix = match[:-1] if match and match.endswith("*") else (match or "")
        for key in list(self.zsets):
            if key.startswith(prefix):
                yield key

    async def aclose(self):
        self.closed = True


class TestRedisFloodStore:
    """The Redis backend is what keeps the limit correct across workers."""

    @pytest.fixture
    def store(self):
        return RedisFloodStore(FakeRedis())

    async def test_counts_hits_in_the_window(self, store):
        for expected in (1, 2, 3, 4):
            assert await store.hit(1, 1, 1000.0, 3.0) == expected

    async def test_expires_hits_older_than_the_window(self, store):
        await store.hit(1, 1, 1000.0, 3.0)
        await store.hit(1, 1, 1001.0, 3.0)
        # 10 seconds later, both earlier hits are outside the 3s window.
        assert await store.hit(1, 1, 1011.0, 3.0) == 1

    async def test_same_tick_messages_are_not_collapsed(self, store):
        # Identical timestamps would collide on score alone; unique members stop that.
        for _ in range(5):
            await store.hit(1, 1, 1000.0, 3.0)
        assert await store.hit(1, 1, 1000.0, 3.0) == 6

    async def test_users_and_groups_are_isolated(self, store):
        await store.hit(1, 1, 1000.0, 3.0)
        await store.hit(1, 1, 1000.0, 3.0)
        assert await store.hit(1, 2, 1000.0, 3.0) == 1
        assert await store.hit(2, 1, 1000.0, 3.0) == 1

    async def test_keys_get_a_ttl_so_they_do_not_leak(self, store):
        await store.hit(1, 1, 1000.0, 3.0)
        assert store._client.expiries["aegis:flood:1:1"] >= 3

    async def test_reset_user_deletes_only_that_key(self, store):
        client = store._client
        await store.hit(1, 1, 1000.0, 3.0)
        await store.hit(1, 2, 1000.0, 3.0)
        await store.reset_user(1, 1)
        assert "aegis:flood:1:1" not in client.zsets
        assert "aegis:flood:1:2" in client.zsets

    async def test_reset_group_removes_every_user_in_that_group(self, store):
        client = store._client
        await store.hit(1, 1, 1000.0, 3.0)
        await store.hit(1, 2, 1000.0, 3.0)
        await store.hit(2, 1, 1000.0, 3.0)
        await store.reset_group(1)
        assert "aegis:flood:1:1" not in client.zsets
        assert "aegis:flood:1:2" not in client.zsets
        assert "aegis:flood:2:1" in client.zsets

    async def test_close_releases_the_client(self, store):
        client = store._client
        await store.close()
        assert client.closed is True


class _BrokenStore:
    """A shared backend that is always down."""

    name = "broken"

    async def hit(self, *args, **kwargs):
        raise RuntimeError("shared store unavailable")

    async def reset_user(self, *args, **kwargs):
        raise RuntimeError("shared store unavailable")

    async def reset_group(self, *args, **kwargs):
        raise RuntimeError("shared store unavailable")

    async def close(self):
        return None


class TestGracefulDegradation:
    async def test_store_failure_falls_back_to_local_memory(self):
        flood.configure_store(_BrokenStore())
        # Protection keeps working locally rather than failing open.
        for _ in range(4):
            assert await flood.check_flood(
                1, 1, msg_limit=5, window_seconds=3.0, now=1000.0
            ) is False
        assert await flood.check_flood(
            1, 1, msg_limit=5, window_seconds=3.0, now=1000.0
        ) is True


class TestStoreSelection:
    async def test_uses_memory_when_no_redis_url_is_configured(self, monkeypatch):
        monkeypatch.setattr(flood.settings, "REDIS_URL", "")
        store = await flood.init_flood_store()
        assert store.name == "memory"

    async def test_falls_back_to_memory_when_redis_is_unreachable(self, monkeypatch):
        # Nothing listens on this port, so the connection fails fast.
        monkeypatch.setattr(flood.settings, "REDIS_URL", "redis://127.0.0.1:6390/0")
        store = await flood.init_flood_store()
        assert store.name == "memory"
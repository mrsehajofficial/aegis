"""
reputation.py — Cross-group spam fingerprint network.

The strategic wedge: every group running Aegis contributes anonymized spam
fingerprints to a shared reputation feed, so a spam campaign that lands in one
group is pre-flagged in every other group within milliseconds.

Privacy by construction — only a SHA-256 of the *normalised* text is stored,
never the content itself:

* The hash is one-way: a fingerprint cannot be turned back into a message.
* Normalisation (:func:`app.anti_spam.normalize.normalize`) folds the evasions
  spammers rely on — zero-width characters, homoglyphs, leetspeak, repeats —
  into the hash, so "s<ZWSP>pam", "spammm" and fullwidth "spam" all
  fingerprint identically.
* Participation is implicit opt-in: fingerprints are only recorded when a
  group's admin has enabled anti-spam, and only after a spam *verdict*.

A message is treated as known spam when the same fingerprint was flagged in at
least ``FLAG_THRESHOLD`` *other* groups within ``TTL_SECONDS`` (24 h). The
origin group is excluded from the count so a group's own verdicts cannot create
a feedback loop, and one noisy admin cannot poison the network alone.

Backends mirror ``flood.py``:

* :class:`InMemoryReputationStore` — the default; works cross-group within one
  process, which already covers every single-worker deployment.
* :class:`RedisReputationStore` — shares fingerprints across workers and
  restarts, and between multiple bots pointed at the same ``REDIS_URL``.
"""
import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Protocol, Tuple

from app.config.settings import settings

logger = logging.getLogger(__name__)

# How many *other* groups must flag a fingerprint before it is treated as spam
# here. Two keeps a single over-eager admin powerless; a genuine spam campaign
# crosses this almost instantly.
FLAG_THRESHOLD = 2

# Fingerprints older than this stop counting. One day matches how long a spam
# campaign stays useful; Redis expiry prunes automatically at the same age.
TTL_SECONDS = 24 * 3600

# Never hash more than this — bounded work per message, same fingerprint for
# long essays since spammers rarely differ beyond their first paragraph.
_MAX_TEXT_LEN = 2000


def normalize_text_for_fingerprint(text: str) -> str:
    """Normalise text before hashing (folds evasion tricks), capped in length."""
    from app.anti_spam.normalize import normalize

    return normalize(text)[:_MAX_TEXT_LEN]


def fingerprint(text: str) -> str:
    """
    One-way SHA-256 of the normalised text (never the raw content).

    .. note::
       This is an unsalted hash of normalised text. Salting and
       pseudonymous tokens are planned for a future shared-reputation feed; they
       are not yet implemented and :data:`settings.REPUTATION_FEED_URL` remains
       unused.
    """
    return hashlib.sha256(
        normalize_text_for_fingerprint(text).encode("utf-8")
    ).hexdigest()


class ReputationStore(Protocol):
    """Backend contract for the fingerprint network."""

    name: str

    async def flag(self, fp: str, chat_id: int, now: float, ttl_seconds: int) -> None:
        """Record that ``chat_id`` flagged ``fp`` at time ``now``."""
        ...

    async def groups_for(
        self, fp: str, own_chat_id: int, now: float, ttl_seconds: int
    ) -> List[int]:
        """Distinct group IDs (excluding ``own_chat_id``) that flagged ``fp``."""
        ...

    async def forget_chat(self, chat_id: int) -> None:
        """Withdraw every fingerprint a group contributed (e.g. on opt-out)."""
        ...

    async def ping(self) -> bool:
        """True when the backend is reachable (used by /health)."""
        ...

    async def close(self) -> None:
        """Release any resources held by the backend."""
        ...


class InMemoryReputationStore:
    """Per-process fingerprint store. Works cross-group within one worker."""

    name = "memory"

    def __init__(self) -> None:
        # {fingerprint: [(timestamp, chat_id), ...]}
        self._flags: Dict[str, Deque[Tuple[float, int]]] = defaultdict(deque)

    def _prune(self, fp: str, now: float, ttl_seconds: int) -> None:
        entries = self._flags.get(fp)
        if not entries:
            return
        cutoff = now - ttl_seconds
        while entries and entries[0][0] < cutoff:
            entries.popleft()
        if not entries:
            self._flags.pop(fp, None)

    async def flag(self, fp: str, chat_id: int, now: float, ttl_seconds: int) -> None:
        self._prune(fp, now, ttl_seconds)
        self._flags[fp].append((now, chat_id))

    async def groups_for(
        self, fp: str, own_chat_id: int, now: float, ttl_seconds: int
    ) -> List[int]:
        self._prune(fp, now, ttl_seconds)
        seen: Dict[int, None] = {}
        for _, chat_id in self._flags.get(fp, ()):
            if chat_id != own_chat_id:
                # Dict keys dedupe and keep insertion order.
                seen[chat_id] = None
        return list(seen)

    async def forget_chat(self, chat_id: int) -> None:
        for fp in list(self._flags):
            remaining = deque(
                (ts, cid) for ts, cid in self._flags[fp] if cid != chat_id
            )
            if remaining:
                self._flags[fp] = remaining
            else:
                self._flags.pop(fp, None)

    async def close(self) -> None:
        self._flags.clear()

    async def ping(self) -> bool:
        return True


class RedisReputationStore:
    """
    Shared fingerprint store in Redis, so every worker (and every bot sharing
    the same ``REDIS_URL``) sees the same reputation feed.

    Each fingerprint is a sorted set with one member per flag event:
    ``score = timestamp``, ``member = "<chat_id>:<timestamp>"``. A distinct
    member per event means repeated flags from one group are kept separately
    and ``groups_for`` dedupes on the chat ID prefix.
    """

    name = "redis"

    def __init__(self, client) -> None:
        self._client = client
        # aegis:* is already the flood store's family; rep: keeps them apart.
        self._prefix = "aegis:rep:"

    def _key(self, fp: str) -> str:
        return f"{self._prefix}{fp}"

    async def flag(self, fp: str, chat_id: int, now: float, ttl_seconds: int) -> None:
        key = self._key(fp)
        member = f"{chat_id}:{now:.6f}"
        await self._client.zadd(key, {member: now})
        # Expire the whole fingerprint one TTL after the latest flag.
        await self._client.expire(key, ttl_seconds)

    async def groups_for(
        self, fp: str, own_chat_id: int, now: float, ttl_seconds: int
    ) -> List[int]:
        key = self._key(fp)
        cutoff = now - ttl_seconds
        # Drop aged-out entries first so long-lived keys cannot grow forever.
        await self._client.zremrangebyscore(key, "-inf", cutoff)
        members = await self._client.zrangebyscore(key, cutoff, "+inf")
        seen: Dict[int, None] = {}
        for member in members:
            try:
                chat_id = int(str(member).split(":", 1)[0])
            except ValueError:
                continue
            if chat_id != own_chat_id:
                seen[chat_id] = None
        return list(seen)

    async def forget_chat(self, chat_id: int) -> None:
        # Scanning the keyspace is acceptable here: opt-out is rare, and the
        # alternative (a per-group index) complicates every hot-path read.
        cursor = 0
        prefix = self._prefix
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor, match=f"{prefix}*", count=100
            )
            for key in keys:
                members = await self._client.zrange(key, 0, -1)
                doomed = [
                    m for m in members if str(m).startswith(f"{chat_id}:")
                ]
                if doomed:
                    await self._client.zrem(key, *doomed)
            if cursor == 0:
                break

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except AttributeError:
            await self._client.close()

    async def ping(self) -> bool:
        await self._client.ping()
        return True


_store: ReputationStore = InMemoryReputationStore()
# Degradation target when the shared backend errors mid-flight, mirroring
# flood.py: a Redis outage must never disable protection outright.
_fallback: ReputationStore = InMemoryReputationStore()


def get_reputation_store() -> ReputationStore:
    return _store


def configure_store(store: ReputationStore) -> None:
    """Swap the active backend. Used by init_reputation_store() and by tests."""
    global _store
    _store = store


def configure_fallback(store: ReputationStore) -> None:
    """Swap the degradation target. Used by tests."""
    global _fallback
    _fallback = store


async def init_reputation_store() -> ReputationStore:
    """
    Select the backend from configuration. Call once during startup.

    Redis is preferred when ``REDIS_URL`` is set — it is what turns this from a
    single-bot feature into an actual network between deployments. Any
    connection problem degrades to the in-memory store with a warning, because
    a cache outage should not stop the bot from protecting groups.
    """
    url = (getattr(settings, "REDIS_URL", "") or "").strip()
    if not url:
        configure_store(InMemoryReputationStore())
        logger.info(
            "Reputation store: in-memory. Set REDIS_URL to share fingerprints "
            "across workers and deployments."
        )
        return _store
    try:
        # Imported lazily so the redis package stays optional at runtime.
        from redis.asyncio import Redis

        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        configure_store(RedisReputationStore(client))
        logger.info("Reputation store: Redis (fingerprints shared).")
    except Exception as e:
        logger.warning(
            f"Redis unavailable for reputation ({type(e).__name__}: {e}) — "
            "falling back to the in-memory store."
        )
        configure_store(InMemoryReputationStore())
    return _store


async def close_reputation_store() -> None:
    """Release the active backend on shutdown."""
    try:
        await _store.close()
    except Exception as e:
        logger.debug(f"Reputation store close failed: {e}")


async def record_spam(
    chat_id: int, text: str, now: Optional[float] = None
) -> None:
    """
    Contribute a fingerprint to the network after a spam verdict.

    Callers must have already decided the message is spam, so over-reporting
    bugs surface as missing/extra records in tests rather than silent
    false positives in production groups.
    """
    if not text:
        return
    fp = fingerprint(text)
    if now is None:
        now = time.time()
    try:
        await _store.flag(fp, chat_id, now, TTL_SECONDS)
    except Exception as e:
        logger.warning(
            f"Reputation store '{_store.name}' error on record ({e}); "
            "trying local fallback."
        )
        await _fallback.flag(fp, chat_id, now, TTL_SECONDS)


async def known_spam_groups(
    text: str,
    own_chat_id: int,
    now: Optional[float] = None,
) -> int:
    """
    How many *other* groups flagged this text's fingerprint recently.

    Returns 0 for empty text (nothing to hash) and on backend errors — a
    reputation outage must never block an ordinary message.
    """
    if not text:
        return 0
    fp = fingerprint(text)
    if now is None:
        now = time.time()
    try:
        return len(await _store.groups_for(fp, own_chat_id, now, TTL_SECONDS))
    except Exception as e:
        logger.warning(
            f"Reputation store '{_store.name}' error on lookup ({e}); "
            "using local fallback."
        )
        try:
            return len(
                await _fallback.groups_for(fp, own_chat_id, now, TTL_SECONDS)
            )
        except Exception as e2:
            logger.warning(f"Reputation fallback also failed ({e2}).")
            return 0


async def withdraw_chat(chat_id: int) -> None:
    """Remove a group's contributions (called when anti-spam is turned off)."""
    for store in (_store, _fallback):
        try:
            await store.forget_chat(chat_id)
        except Exception as e:
            logger.debug(f"Reputation withdraw failed on {store.name}: {e}")

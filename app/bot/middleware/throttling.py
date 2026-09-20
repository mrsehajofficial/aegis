"""
throttling.py — Simple in-memory rate limiter.

Used to prevent command spam. For V0.5 this will be replaced with the
sliding-window anti-flood detector in app/anti_spam/flood.py.
"""
import time
import logging
from collections import defaultdict
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Structure: {(user_id, command): (count, window_start)}
_rate_store: Dict[Tuple[int, str], Tuple[int, float]] = defaultdict(lambda: (0, 0.0))

# Default: max 5 uses per 30 seconds per user per command
DEFAULT_MAX = 5
DEFAULT_WINDOW = 30.0

# Cleanup threshold: purge expired keys when store grows beyond this size.
_CLEANUP_THRESHOLD = 2000


def _maybe_cleanup(now: float) -> None:
    """Remove entries whose windows have expired (runs infrequently)."""
    if len(_rate_store) < _CLEANUP_THRESHOLD:
        return
    stale = [k for k, (_, ws) in list(_rate_store.items()) if now - ws > DEFAULT_WINDOW * 2]
    for k in stale:
        _rate_store.pop(k, None)


def check_rate_limit(
    user_id: int,
    command: str,
    max_calls: int = DEFAULT_MAX,
    window_seconds: float = DEFAULT_WINDOW,
) -> bool:
    """
    Returns True if the call is allowed, False if the user is rate-limited.
    This is a simple in-memory counter — it resets on bot restart.
    """
    key = (user_id, command)
    now = time.monotonic()
    _maybe_cleanup(now)
    count, window_start = _rate_store[key]

    if now - window_start > window_seconds:
        # Window expired — reset
        _rate_store[key] = (1, now)
        return True

    if count >= max_calls:
        logger.debug(f"Rate limit hit: user={user_id} command={command!r} count={count}")
        return False

    _rate_store[key] = (count + 1, window_start)
    return True

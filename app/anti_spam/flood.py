"""
flood.py - Sliding-window flood detector.

Tracks per-user message timestamps in a deque. When a user exceeds the
configured message count within the time window, the flood is triggered.
"""
import time
import logging
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple

logger = logging.getLogger(__name__)

# Per-user message timestamps: {(group_id, user_id): deque of timestamps}
_flood_store: Dict[Tuple[int, int], Deque[float]] = defaultdict(lambda: deque(maxlen=100))

# Default: 5 messages in 3 seconds
DEFAULT_MSG_LIMIT = 5
DEFAULT_WINDOW_SECONDS = 3.0


def check_flood(
    group_id: int,
    user_id: int,
    msg_limit: int = DEFAULT_MSG_LIMIT,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> bool:
    """
    Returns True if the user is flooding (exceeded msg_limit within window_seconds).
    Records the current message timestamp.
    """
    key = (group_id, user_id)
    now = time.monotonic()
    timestamps = _flood_store[key]

    # Remove timestamps outside the window
    while timestamps and now - timestamps[0] > window_seconds:
        timestamps.popleft()

    timestamps.append(now)

    if len(timestamps) >= msg_limit:
        logger.debug(
            f"Flood detected: group={group_id} user={user_id} "
            f"count={len(timestamps)} limit={msg_limit}"
        )
        return True
    return False


def reset_user(group_id: int, user_id: int) -> None:
    """Clear flood tracking for a user (e.g., after mute)."""
    key = (group_id, user_id)
    if key in _flood_store:
        _flood_store[key].clear()


def reset_group(group_id: int) -> None:
    """Clear all flood tracking for a group."""
    keys_to_remove = [k for k in _flood_store if k[0] == group_id]
    for key in keys_to_remove:
        del _flood_store[key]

import logging
import time
from typing import Optional, List, Dict, Tuple, Set

from app.database.connection import get_session
from app.database.models.business import BusinessConnection, BusinessRule
from app.database.repositories.business import BusinessRepository

logger = logging.getLogger(__name__)

# Default starter templates for newly connected business accounts
DEFAULT_BUSINESS_RULES = [
    {
        "trigger": "price",
        "response": "Hey there, let's discuss your requirements first then we'll decide what's the best pricing for you!",
        "match_type": "contains",
    },
    {
        "trigger": "hours",
        "response": "⏰ I am available Monday to Friday, 9:00 AM to 6:00 PM. Messages outside these hours will be answered as soon as I am back.",
        "match_type": "contains",
    },
    {
        "trigger": "support",
        "response": "🛠️ Need help? Please describe your issue in detail and I will reply to you shortly.",
        "match_type": "contains",
    },
    {
        "trigger": "hello",
        "response": "👋 Hello! Thanks for reaching out. How can I help you today?",
        "match_type": "contains",
    },
]

# In-memory debounce/cooldown to prevent rapid spam or bot loops
# (connection_id, chat_id) -> last reply timestamp
_chat_last_reply: Dict[Tuple[str, int], float] = {}
# (connection_id, chat_id) -> last away/fallback reply timestamp (15 min cooldown)
_chat_last_away: Dict[Tuple[str, int], float] = {}
# Set of (connection_id, chat_id) that have received a greeting in current session
_greeted_chats: Set[Tuple[str, int]] = set()

COOLDOWN_BETWEEN_REPLIES_SEC = 2.0
AWAY_MESSAGE_COOLDOWN_SEC = 900.0  # 15 minutes


def _clean_old_cache(now: float) -> None:
    """Housekeeping for in-memory cooldown trackers.

    Takes the caller's clock reading instead of sampling its own, so an injected
    ``now`` drives the whole evaluation against one consistent timeline.
    """
    # Clean entries older than 1 hour
    for key in list(_chat_last_reply.keys()):
        if now - _chat_last_reply[key] > 3600:
            _chat_last_reply.pop(key, None)
    for key in list(_chat_last_away.keys()):
        if now - _chat_last_away[key] > 3600:
            _chat_last_away.pop(key, None)


async def register_business_connection(
    connection_id: str,
    user_id: int,
    user_chat_id: Optional[int],
    can_reply: bool,
    is_enabled: bool,
) -> BusinessConnection:
    """
    Upsert a business connection record and seed default rules if first time.
    """
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.upsert_connection(
            connection_id=connection_id,
            user_id=user_id,
            user_chat_id=user_chat_id,
            can_reply=can_reply,
            is_enabled=is_enabled,
        )

        # If user has no rules yet and connection is enabled, seed defaults
        rules = await repo.get_rules(user_id=user_id)
        if not rules and is_enabled:
            for item in DEFAULT_BUSINESS_RULES:
                await repo.add_or_update_rule(
                    user_id=user_id,
                    trigger=item["trigger"],
                    response=item["response"],
                    match_type=item["match_type"],
                    connection_id=connection_id,
                )
            logger.info("Seeded default business auto-replies for user %d", user_id)

        await session.commit()
        return conn


async def get_business_connection_for_user(user_id: int) -> Optional[BusinessConnection]:
    """Retrieve the business connection for a given Telegram user ID."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        return await repo.get_connection_by_user_id(user_id)


async def get_business_connection_by_id(connection_id: str) -> Optional[BusinessConnection]:
    """Retrieve connection by connection_id."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        return await repo.get_connection_by_id(connection_id)


async def toggle_auto_reply(user_id: int) -> Optional[bool]:
    """Toggle master auto-reply switch. Returns new boolean state, or None if no connection."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_user_id(user_id)
        if not conn:
            return None
        conn.auto_reply_enabled = not conn.auto_reply_enabled
        await session.commit()
        return conn.auto_reply_enabled


async def toggle_greeting(user_id: int) -> Optional[bool]:
    """Toggle greeting message switch. Returns new boolean state, or None if no connection."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_user_id(user_id)
        if not conn:
            return None
        conn.greeting_enabled = not conn.greeting_enabled
        await session.commit()
        return conn.greeting_enabled


async def toggle_away(user_id: int) -> Optional[bool]:
    """Toggle away/out-of-office fallback switch. Returns new boolean state, or None if no connection."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_user_id(user_id)
        if not conn:
            return None
        conn.away_enabled = not conn.away_enabled
        await session.commit()
        return conn.away_enabled


async def set_greeting_message(user_id: int, message: Optional[str]) -> bool:
    """Set greeting text for the business account."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_user_id(user_id)
        if not conn:
            return False
        conn.greeting_message = message
        if message:
            conn.greeting_enabled = True
        await session.commit()
        return True


async def set_away_message(user_id: int, message: Optional[str]) -> bool:
    """Set away / out-of-office message for the business account."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_user_id(user_id)
        if not conn:
            return False
        conn.away_message = message
        if message:
            conn.away_enabled = True
        await session.commit()
        return True


async def add_business_rule(
    user_id: int,
    trigger: str,
    response: str,
    match_type: str = "contains",
) -> BusinessRule:
    """Add or update an auto-reply rule for the user's business account."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_user_id(user_id)
        conn_id = conn.connection_id if conn else None
        rule = await repo.add_or_update_rule(
            user_id=user_id,
            trigger=trigger,
            response=response,
            match_type=match_type,
            connection_id=conn_id,
        )
        await session.commit()
        return rule


async def delete_business_rule(user_id: int, trigger: str) -> bool:
    """Remove a business auto-reply rule."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        deleted = await repo.delete_rule(user_id=user_id, trigger=trigger)
        await session.commit()
        return deleted


async def get_business_rules(user_id: int) -> List[BusinessRule]:
    """Retrieve all business rules for a user."""
    async with get_session() as session:
        repo = BusinessRepository(session)
        return list(await repo.get_rules(user_id=user_id))


async def evaluate_business_message(
    connection_id: str,
    chat_id: int,
    from_user_id: int,
    text: str,
    now: Optional[float] = None,
) -> Optional[str]:
    """
    Evaluate an incoming message in a Telegram Business private chat.
    Returns the automated response text to send on behalf of the user, or None.

    Key safety behaviors:
    1. Ignores messages sent by the business owner themself.
    2. Respects auto_reply_enabled, is_enabled, and can_reply.
    3. Throttles rapid replies (anti-loop).
    4. Evaluates keyword rules (contains / exact).
    5. Falls back to greeting / away if applicable.

    ``now`` is injectable so tests can advance time without patching the clock.
    """
    if now is None:
        now = time.monotonic()
    _clean_old_cache(now)
    cache_key = (connection_id, chat_id)

    async with get_session() as session:
        repo = BusinessRepository(session)
        conn = await repo.get_connection_by_id(connection_id)
        if not conn:
            logger.debug("Business connection %s not found in database", connection_id)
            return None

        # Check enabled and reply rights
        if not conn.is_enabled or not conn.can_reply or not conn.auto_reply_enabled:
            return None

        # Critical: Do NOT reply to messages sent by the account owner
        if from_user_id == conn.user_id:
            logger.debug("Ignoring business message sent by account owner %d", from_user_id)
            return None

        # Anti-spam debounce: avoid sending multiple replies in quick succession to same chat.
        # No entry means "never replied", which must not debounce: a 0.0 default
        # would look like a reply sent at clock zero, i.e. *inside* the cooldown
        # on any machine whose monotonic clock is younger than the cooldown.
        last_reply = _chat_last_reply.get(cache_key)
        if last_reply is not None and now - last_reply < COOLDOWN_BETWEEN_REPLIES_SEC:
            logger.debug("Business reply debounced for chat %d (within cooldown)", chat_id)
            return None

        normalized_text = (text or "").strip().lower()
        if not normalized_text:
            return None

        # 1. Match Keyword Rules
        rules = await repo.get_rules(user_id=conn.user_id, enabled_only=True)
        for rule in rules:
            trig = (rule.trigger or "").strip().lower()
            if not trig:
                continue

            matched = False
            if rule.match_type == "exact":
                matched = normalized_text == trig
            else:  # "contains" default
                matched = trig in normalized_text

            if matched:
                _chat_last_reply[cache_key] = now
                logger.info(
                    "Business auto-reply triggered for keyword %r in chat %d via connection %s",
                    trig,
                    chat_id,
                    connection_id,
                )
                return rule.response

        # 2. Greeting Message: If enabled and chat has not been greeted yet
        if conn.greeting_enabled and conn.greeting_message:
            if cache_key not in _greeted_chats:
                _greeted_chats.add(cache_key)
                _chat_last_reply[cache_key] = now
                logger.info("Sent business greeting message to chat %d via connection %s", chat_id, connection_id)
                return conn.greeting_message

        # 3. Away / Out-of-Office Fallback
        if conn.away_enabled and conn.away_message:
            # Same sentinel rule as the debounce above: no entry means the
            # cooldown has elapsed, otherwise a freshly booted host (small
            # monotonic clock) would swallow the first away reply for 15 minutes.
            last_away = _chat_last_away.get(cache_key)
            if last_away is None or now - last_away >= AWAY_MESSAGE_COOLDOWN_SEC:
                _chat_last_away[cache_key] = now
                _chat_last_reply[cache_key] = now
                logger.info("Sent business away message to chat %d via connection %s", chat_id, connection_id)
                return conn.away_message

    return None

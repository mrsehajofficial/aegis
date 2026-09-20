"""
auth.py — Chat and user context extraction utilities.

Role hierarchy enforced: owner > admin > moderator > member.
SUPER_ADMIN_IDS from settings always pass admin checks.

The critical fix here: ``is_admin_or_above`` no longer relies solely on the
local database role column (which could be stale or never populated).
For any user not already known as admin/owner in the DB, it calls the live
Telegram Bot API (``get_chat_member``) and self-heals the database if Telegram
says they are an admin.  Results are cached for 60 seconds per (chat, user)
pair so the network cost is negligible.
"""
import logging
import time
from typing import Dict, Optional, Tuple
from telegram import Update, Chat, User
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository

logger = logging.getLogger(__name__)

# Role hierarchy (higher index = more privileged)
ROLE_HIERARCHY = ["member", "moderator", "admin", "owner"]

# TTL for the in-memory Telegram admin check cache (seconds).
_ADMIN_CHECK_TTL = 60
# {(chat_id, user_id): (expires_at, is_admin_bool)}
_tg_admin_cache: Dict[Tuple[int, int], Tuple[float, bool]] = {}


def role_rank(role: str) -> int:
    """Return numeric rank of a role string. Unknown roles get rank 0."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return 0


def is_super_admin(user_id: Optional[int]) -> bool:
    """True if user_id is in SUPER_ADMIN_IDS."""
    return user_id is not None and user_id in (settings.SUPER_ADMIN_IDS or [])


async def _is_tg_admin(chat_id: int, user_id: int, bot) -> bool:
    """
    Check via Telegram Bot API whether ``user_id`` is an admin/creator in
    ``chat_id``.  Results are cached per (chat, user) for ``_ADMIN_CHECK_TTL``
    seconds to avoid hammering the API on every message.
    """
    key = (chat_id, user_id)
    now = time.monotonic()
    cached = _tg_admin_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    try:
        member = await bot.get_chat_member(chat_id, user_id)
        result = member.status in ("administrator", "creator")
    except Exception as e:
        logger.debug("get_chat_member(%s, %s) failed: %s", chat_id, user_id, e)
        # On error conservatively fall back to whatever is cached, else False.
        return cached[1] if cached else False

    _tg_admin_cache[key] = (now + _ADMIN_CHECK_TTL, result)
    return result


async def get_calling_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE = None) -> str:
    """
    Resolve the calling user's role for the current group.

    Resolution order:
      1. Super-admin always resolves to 'owner'.
      2. Local DB role (if stored as admin/owner — avoid a network call).
      3. Live Telegram API check — self-heals the DB if Telegram says admin.
    Falls back to 'member'.
    """
    user = update.effective_user
    chat = update.effective_chat

    if user is None:
        return "member"
    if is_super_admin(user.id):
        return "owner"
    if chat is None or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return "member"

    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)

        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            return "member"

        member = await member_repo.get_member(group.id, user.id)
        db_role = member.role if member else "member"

        # If DB already has an elevated role, trust it (admin-sync keeps it fresh).
        if role_rank(db_role) >= role_rank("admin"):
            return db_role

        # DB says member/moderator — verify against live Telegram data.
        if context is not None:
            try:
                is_tg = await _is_tg_admin(chat.id, user.id, context.bot)
                if is_tg:
                    # Self-heal: promote in DB so subsequent checks are faster.
                    tg_member = await context.bot.get_chat_member(chat.id, user.id)
                    new_role = "owner" if tg_member.status == "creator" else "admin"
                    await member_repo.upsert_member(
                        group.id, user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        role=new_role,
                        force_role=True,
                    )
                    await session.commit()
                    return new_role
            except Exception as e:
                logger.debug("Live admin check failed for user %s: %s", user.id, e)

        return db_role


async def is_admin_or_above(update: Update, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    """True if caller is admin/owner, or a super admin."""
    user = update.effective_user
    if user is not None and is_super_admin(user.id):
        return True
    role = await get_calling_user_role(update, context)
    return role_rank(role) >= role_rank("admin")


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the calling user is an admin. If not, reply with an error and return False.
    Usage: if not await require_admin(update, context): return
    """
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html(
            "<b>Access denied.</b>\nThis command requires admin privileges."
        )
        return False
    return True

"""
auth.py — Chat and user context extraction utilities.

Role hierarchy enforced: owner > admin > moderator > member.
SUPER_ADMIN_IDS from settings always pass admin checks.
"""
import logging
from typing import Optional, Tuple
from telegram import Update, Chat, User
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository

logger = logging.getLogger(__name__)

# Role hierarchy (higher index = more privileged)
ROLE_HIERARCHY = ["member", "moderator", "admin", "owner"]


def role_rank(role: str) -> int:
    """Return numeric rank of a role string. Unknown roles get rank 0."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return 0


def is_super_admin(user_id: Optional[int]) -> bool:
    """True if user_id is in SUPER_ADMIN_IDS."""
    return user_id is not None and user_id in (settings.SUPER_ADMIN_IDS or [])


async def get_calling_user_role(update: Update) -> str:
    """
    Resolve the calling user's stored role for the current group.
    Super admins always resolve to 'owner'. Falls back to 'member'.
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
        return member.role if member else "member"


async def is_admin_or_above(update: Update) -> bool:
    """True if caller is admin/owner, or a super admin."""
    user = update.effective_user
    if user is not None and is_super_admin(user.id):
        return True
    role = await get_calling_user_role(update)
    return role_rank(role) >= role_rank("admin")


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the calling user is an admin. If not, reply with an error and return False.
    Usage: if not await require_admin(update, context): return
    """
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html(
            "<b>Access denied.</b>\nThis command requires admin privileges."
        )
        return False
    return True

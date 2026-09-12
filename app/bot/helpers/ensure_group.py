"""
ensure_group helper — guarantees the group row + settings exist before any
group command runs. Self-heals when my_chat_member was missed (bot added offline).
"""
import logging
from typing import Optional
from telegram import Chat
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.services.groups import register_or_update_group, sync_group_admins

logger = logging.getLogger(__name__)


async def ensure_group_registered(chat: Chat, bot=None) -> Optional[int]:
    """
    Return internal group_id, registering + syncing admins on first use if needed.
    Returns None only if registration itself fails.
    """
    async with get_session() as session:
        group = await GroupRepository(session).get_by_telegram_id(chat.id)
        if group is not None:
            return group.id
    try:
        db_id = await register_or_update_group(chat)
        if bot is not None:
            try:
                await sync_group_admins(chat, bot)
            except Exception as e:
                logger.warning(f"Admin sync failed on ensure for {chat.id}: {e}")
        return db_id
    except Exception as e:
        logger.error(f"ensure_group_registered failed for {chat.id}: {e}", exc_info=True)
        return None


def _limited(user_id: int, command: str) -> bool:
    from app.bot.middleware.throttling import check_rate_limit
    return not check_rate_limit(user_id=user_id, command=command)


async def guard(update, context: ContextTypes.DEFAULT_TYPE, command: str) -> Optional[int]:
    """
    Shared pre-flight for every group command:
      1. Must be a group/supergroup.
      2. Rate-limit per user per command (6/min).
      3. Ensure group registered (self-heal).
    Returns internal group_id, or None if the handler should stop
    (a user-facing message has already been sent).
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if chat is None or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        if msg:
            await msg.reply_text("This command only works in groups.")
        return None
    if user and _limited(user.id, command):
        if msg:
            await msg.reply_text("You are sending commands too quickly. Please wait a moment.")
        return None
    db_id = await ensure_group_registered(chat, context.bot if context else None)
    if db_id is None and msg:
        await msg.reply_text("Group registration failed. Please try again shortly.")
    return db_id

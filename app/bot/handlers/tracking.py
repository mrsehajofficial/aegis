"""
tracking.py — Keeps the per-group member cache fresh.

Every member message (plus the replied-to user) upserts the member row so
that @username lookups in moderation commands can resolve regular users,
which Telegram's getChat API cannot do reliably.
"""
import logging

from telegram import Chat, Update
from telegram.ext import ContextTypes

from app.bot.helpers.ensure_group import ensure_group_registered
from app.services.members import get_or_create_member

logger = logging.getLogger(__name__)


async def track_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Record every member seen in a group message (sender + reply target)."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return
    # Cheap when the group is already registered; self-heals otherwise.
    group_id = await ensure_group_registered(chat)
    if group_id is None:
        return  # unregistered — get_or_create_member would only log noise
    user = update.effective_user
    replied = msg.reply_to_message.from_user if msg.reply_to_message else None
    try:
        if user and not user.is_bot:
            await get_or_create_member(chat, user)
        if replied and not replied.is_bot and (user is None or replied.id != user.id):
            await get_or_create_member(chat, replied)
    except Exception as e:
        logger.debug(f"track_members failed in chat {chat.id}: {e}")
"""
actions.py - Anti-spam/flood actions.

Handles the consequences of detected spam/flood:
- Delete offending messages
- Mute the offender temporarily
- Warn the offender
"""
import logging
from datetime import timedelta
from typing import Optional

from telegram import Chat, ChatPermissions, Message
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def delete_message_safely(message: Message) -> bool:
    """Delete a message, swallowing errors."""
    try:
        await message.delete()
        return True
    except Exception as e:
        logger.debug(f"Could not delete message {message.message_id}: {e}")
        return False


async def mute_user(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    duration: timedelta = timedelta(minutes=5),
) -> bool:
    """
    Mute a user for the specified duration.
    Returns True on success.
    """
    from datetime import datetime, timezone
    until = datetime.now(timezone.utc) + duration
    perms = ChatPermissions(
        can_send_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=perms,
            until_date=until,
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to mute user {user_id} in chat {chat_id}: {e}")
        return False


async def ban_user(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> bool:
    """Ban a user from the chat. Returns True on success."""
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        return True
    except Exception as e:
        logger.warning(f"Failed to ban user {user_id} in chat {chat_id}: {e}")
        return False


async def notify_admins(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
) -> None:
    """Send a notification to the group (admins will see it)."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.debug(f"Could not notify chat {chat_id}: {e}")

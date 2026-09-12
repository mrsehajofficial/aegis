"""Resolve a target user from a lookup token (@username or numeric ID).

The Telegram Bot API has two limitations worked around here:

1. getChatMember does not accept @usernames, so a @username must first be
   resolved to a numeric user ID via getChat.
2. getChat only reliably resolves *bots, channels and supergroups* — for
   regular users it usually returns "chat not found". We therefore keep a
   per-group username cache in the members table (populated by the message
   tracker) and fall back to it when getChat can't resolve the username.

If the final membership lookup still fails (e.g. privacy settings hide the
member), the best available identity is returned so that commands like
"/mute @user 10m" work without needing a reply to their message.
"""
import logging
from typing import Optional, Union

from telegram import ChatFullInfo, User
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository

logger = logging.getLogger(__name__)


def _user_from_member_row(member) -> User:
    """Build a best-effort User object from a cached members row."""
    return User(
        id=member.telegram_id,
        is_bot=False,
        first_name=member.first_name or "User",
        last_name=member.last_name,
        username=member.username,
    )


async def _lookup_cached_user(chat_id: int, username: str) -> Optional[User]:
    """Resolve '@username' through the per-group member cache."""
    try:
        async with get_session() as session:
            group = await GroupRepository(session).get_by_telegram_id(chat_id)
            if group is None:
                return None
            member = await MemberRepository(session).get_member_by_username(
                group.id, username)
            if member is None or member.telegram_id is None:
                return None
            return _user_from_member_row(member)
    except Exception as e:
        logger.warning(f"Username cache lookup failed for {username}: {e}")
        return None


async def resolve_user(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    lookup: Union[str, int, None],
) -> Optional[Union[User, ChatFullInfo]]:
    """Resolve '@username' or a numeric user ID to a user object.

    Resolution order for @username:
      1. getChat (works for bots/channels/supergroups).
      2. Per-group members username cache (works for regular users who
         have sent at least one message while the bot was present).
    Returns a User (or ChatFullInfo as fallback), or None if Telegram
    can't resolve the lookup at all.
    """
    if lookup is None:
        return None
    try:
        if isinstance(lookup, str):
            if not lookup.startswith("@"):
                return None
            # Step 1: username -> numeric user ID via getChat
            user_chat = None
            try:
                user_chat = await context.bot.get_chat(lookup)
            except Exception:
                user_chat = None  # common for regular users
            if user_chat is not None:
                # Step 2: numeric ID -> member of this chat
                try:
                    member = await context.bot.get_chat_member(chat_id, user_chat.id)
                except Exception:
                    # Can't verify membership (privacy settings / bot limits),
                    # but the user itself resolved fine — trust getChat.
                    return user_chat
                return member.user
            # getChat failed — fall back to the username cache.
            return await _lookup_cached_user(chat_id, lookup)
        return (await context.bot.get_chat_member(chat_id, lookup)).user
    except Exception:
        return None

import logging
from telegram import Update, Chat
from telegram.ext import ContextTypes, ChatMemberHandler

from app.config.settings import settings
from app.services.groups import register_or_update_group, sync_group_admins, log_bot_added

logger = logging.getLogger(__name__)

_GROUP_TYPES = {Chat.GROUP, Chat.SUPERGROUP}


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fired when the bot's own membership status changes in any chat.
    Used for automatic group registration when the bot is added.
    """
    change = update.my_chat_member
    if change is None:
        return

    chat = change.chat
    new_status = change.new_chat_member.status
    old_status = change.old_chat_member.status

    # Only care about groups and supergroups
    if chat.type not in _GROUP_TYPES:
        return

    actor = change.from_user

    # Bot was added (joined as member or promoted to admin)
    if new_status in ("member", "administrator") and old_status in ("left", "kicked", "restricted"):
        logger.info(
            f"Bot added to group {chat.title!r} (id={chat.id}) "
            f"by @{actor.username or actor.id} as {new_status!r}"
        )
        try:
            await register_or_update_group(chat)
        except Exception as e:
            logger.error(f"Failed to register group {chat.id}: {e}", exc_info=True)
            return

        try:
            await sync_group_admins(chat, context.bot)
        except Exception as e:
            logger.error(f"Failed to sync admins for group {chat.id}: {e}", exc_info=True)

        try:
            await log_bot_added(chat, actor_id=actor.id if actor else None)
        except Exception as e:
            logger.warning(f"Failed to log BOT_ADDED for group {chat.id}: {e}")

        # Greet the group
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"<b>{settings.BOT_NAME} is now active in this group.</b>\n\n"
                    "I'll handle moderation, filters and member management for you.\n"
                    "Every action is logged and reviewable via /logs.\n\n"
                    "Send /help to see the full command list."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not send greeting to group {chat.id}: {e}")

    # Bot was removed or banned
    elif new_status in ("left", "kicked") and old_status in ("member", "administrator"):
        logger.info(
            f"Bot removed from group {chat.title!r} (id={chat.id}) "
            f"by @{actor.username or actor.id if actor else 'unknown'}"
        )
        # We intentionally keep the group data; removal is not data deletion.

    # Bot was promoted to admin while already a member
    elif new_status == "administrator" and old_status == "member":
        logger.info(f"Bot promoted to admin in group {chat.title!r} (id={chat.id})")
        try:
            await sync_group_admins(chat, context.bot)
        except Exception as e:
            logger.error(f"Failed to sync admins after promotion in group {chat.id}: {e}", exc_info=True)

        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"<b>{settings.BOT_NAME} has been granted admin privileges.</b>\n\n"
                    "All moderation actions are now unlocked.\n"
                    "Send /help for the full command list."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not send promotion message to group {chat.id}: {e}")

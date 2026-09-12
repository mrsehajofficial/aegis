"""
group_protection.py - Anti-flood, anti-spam, locks, and blacklist management.
"""
import html
import logging

from telegram import Update, Chat, ChatPermissions
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.database.repositories.protection import BlacklistRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)


LOCK_TYPES = {
    "all": "all content",
    "media": "media",
    "sticker": "stickers",
    "gif": "GIFs",
    "forward": "forwarded messages",
    "url": "links/URLs",
    "mention": "@mentions",
    "photo": "photos",
    "video": "videos",
    "audio": "audio/voice",
    "document": "files/documents",
    "poll": "polls",
    "game": "games",
    "contact": "contacts",
    "location": "locations",
}

LOCK_PERMISSIONS = {
    "media": ["can_send_media_messages"],
    "sticker": ["can_send_other_messages"],
    "gif": ["can_send_other_messages"],
    "photo": ["can_send_media_messages"],
    "video": ["can_send_media_messages"],
    "audio": ["can_send_media_messages"],
    "document": ["can_send_media_messages"],
    "poll": ["can_send_other_messages"],
    "game": ["can_send_other_messages"],
    "url": ["can_add_web_page_previews"],
}


async def setantiflood_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setantiflood") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    args = context.args or []
    if not args or args[0].lower() not in ("on", "off", "enable", "disable", "yes", "no"):
        await update.effective_message.reply_text("Usage: /setantiflood on|off [msg_count] [window_seconds]")
        return
    enabled = args[0].lower() in ("on", "enable", "yes")
    kwargs: dict = {"anti_flood_enabled": enabled}
    if enabled and len(args) >= 2:
        try:
            kwargs["flood_msg_limit"] = max(2, min(20, int(args[1])))
        except ValueError:
            pass
    if enabled and len(args) >= 3:
        try:
            kwargs["flood_window_seconds"] = max(1.0, min(60.0, float(args[2])))
        except ValueError:
            pass
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if g:
            await SettingsRepository(session).update(g.id, **kwargs)
            await session.commit()
    if enabled:
        await update.effective_message.reply_html("<b>Anti-flood enabled.</b>")
    else:
        await update.effective_message.reply_html("<b>Anti-flood disabled.</b>")


async def setantispam_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setantispam") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    args = context.args or []
    if not args or args[0].lower() not in ("on", "off", "enable", "disable", "yes", "no"):
        await update.effective_message.reply_text("Usage: /setantispam on|off [delete|mute|ban]")
        return
    enabled = args[0].lower() in ("on", "enable", "yes")
    kwargs: dict = {"anti_spam_enabled": enabled}
    if enabled and len(args) >= 2:
        action = args[1].lower()
        if action in ("delete", "mute", "ban", "warn"):
            kwargs["spam_action"] = action
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if g:
            await SettingsRepository(session).update(g.id, **kwargs)
            await session.commit()
    if enabled:
        action = kwargs.get("spam_action", "delete")
        await update.effective_message.reply_html(f"<b>Anti-spam enabled.</b> Action: {action}")
    else:
        await update.effective_message.reply_html("<b>Anti-spam disabled.</b>")


async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "lock") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /lock <type>")
        return
    lock_type = context.args[0].lower()
    if lock_type not in LOCK_TYPES:
        await update.effective_message.reply_text(f"Unknown: {lock_type}")
        return
    try:
        if lock_type == "all":
            perms = ChatPermissions.all_permissions()
            for attr in perms.__dict__:
                if not attr.startswith("_") and not callable(getattr(perms, attr, None)):
                    setattr(perms, attr, False)
        else:
            perms = ChatPermissions.all_permissions()
            for perm_attr in LOCK_PERMISSIONS.get(lock_type, []):
                setattr(perms, perm_attr, False)
        await context.bot.set_chat_permissions(chat.id, perms)
        await update.effective_message.reply_html(f"<b>Locked:</b> {LOCK_TYPES[lock_type]}")
    except Exception as e:
        await update.effective_message.reply_text(f"Lock failed: {e}")


async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "unlock") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /unlock <type>")
        return
    lock_type = context.args[0].lower()
    if lock_type not in LOCK_TYPES:
        await update.effective_message.reply_text(f"Unknown: {lock_type}")
        return
    try:
        perms = ChatPermissions.all_permissions()
        await context.bot.set_chat_permissions(chat.id, perms)
        await update.effective_message.reply_html(f"<b>Unlocked:</b> {LOCK_TYPES[lock_type]}")
    except Exception as e:
        await update.effective_message.reply_text(f"Unlock failed: {e}")


async def locktypes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "locktypes") is None:
        return
    lines = ["<b>Lock Types</b>"]
    for lt, desc in LOCK_TYPES.items():
        lines.append(f"  <code>{lt}</code> - {desc}")
    await update.effective_message.reply_html("\n".join(lines))


async def addblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "addblacklist") is None:
        return
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /addblacklist <word> [delete|warn|mute|ban]")
        return
    word = args[0].strip()
    action = args[1].lower() if len(args) > 1 and args[1].lower() in ("delete", "warn", "mute", "ban") else "delete"
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(update.effective_chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        await BlacklistRepository(session).add_word(g.id, word, action)
        await session.commit()
    await update.effective_message.reply_html(f"<b>Blacklist added:</b> <code>{html.escape(word)}</code> ({action})")


async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "blacklist") is None:
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(update.effective_chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        words = await BlacklistRepository(session).get_by_group(g.id)
    if not words:
        await update.effective_message.reply_html("<b>Blacklist</b>\nNo words blacklisted.")
        return
    lines = ["<b>Blacklist</b>"]
    for w in words:
        lines.append(f"  <code>{html.escape(w.word)}</code> - {w.action}")
    await update.effective_message.reply_html("\n".join(lines))


async def rmblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "rmblacklist") is None:
        return
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /rmblacklist <word>")
        return
    word = context.args[0].strip()
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(update.effective_chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        removed = await BlacklistRepository(session).remove_word(g.id, word)
        await session.commit()
    if removed:
        await update.effective_message.reply_html(f"<b>Removed:</b> <code>{html.escape(word)}</code>")
    else:
        await update.effective_message.reply_text(f"'{html.escape(word)}' is not blacklisted.")


async def check_protection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.from_user:
        return
    chat = update.effective_chat
    if not chat or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return
    user_id = message.from_user.id
    try:
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                return
            from app.database.repositories.members import MemberRepository
            member = await MemberRepository(session).get_member(g.id, user_id)
            if member and member.role in ("admin", "owner"):
                return
            settings = await SettingsRepository(session).get_by_group_id(g.id)
            text = (message.text or message.caption or "").lower()
            if text:
                bl_words = await BlacklistRepository(session).get_by_group(g.id)
                for bl_word in bl_words:
                    if bl_word.word.lower() in text:
                        await _handle_blacklist_word(message, context, bl_word.word, bl_word.action)
                        return
            if settings and (settings.anti_flood_enabled or settings.anti_spam_enabled):
                from app.anti_spam import AntiSpamChecker, GroupProtectionSettings
                gp = GroupProtectionSettings(
                    anti_flood_enabled=settings.anti_flood_enabled,
                    anti_spam_enabled=settings.anti_spam_enabled,
                    flood_msg_limit=getattr(settings, "flood_msg_limit", 5) or 5,
                    flood_window_seconds=getattr(settings, "flood_window_seconds", 3.0) or 3.0,
                )
                checker = AntiSpamChecker(context, chat.id, gp)
                await checker.check_message(message)
    except Exception as e:
        logger.debug(f"Protection check error for chat {chat.id}: {e}")


async def _handle_blacklist_word(message, context: ContextTypes.DEFAULT_TYPE, word: str, action: str) -> None:
    await message.delete()
    user_id = message.from_user.id
    if action == "mute":
        from datetime import timedelta
        from app.anti_spam.actions import mute_user
        await mute_user(context, message.chat.id, user_id, timedelta(minutes=10))
    elif action == "ban":
        from app.anti_spam.actions import ban_user
        await ban_user(context, message.chat.id, user_id)

"""
welcome.py — Yuki group commands: rules, welcome/goodbye, settings.
"""
import html
import logging

from telegram import Update, Chat
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)


async def _require_group(update: Update):
    chat = update.effective_chat
    if chat is None or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        if update.effective_message:
            await update.effective_message.reply_text("This command only works in groups.")
        return None
    return chat


async def _get_settings(chat_id: int):
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat_id)
        if not g:
            return None, None
        s = await SettingsRepository(session).get_or_create(g.id)
        # detach values before session closes
        data = {"warn_limit": s.warn_limit, "welcome_enabled": s.welcome_enabled,
                "goodbye_enabled": s.goodbye_enabled, "anti_flood_enabled": s.anti_flood_enabled,
                "anti_spam_enabled": s.anti_spam_enabled, "log_enabled": s.log_enabled,
                "reports_enabled": s.reports_enabled, "rules": s.rules}
        return g, data


async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "welcome") is None:
        return
    chat = update.effective_chat
    _, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    state = "<b>On</b>" if s["welcome_enabled"] else "<b>Off</b>"
    await update.effective_message.reply_html(
        f"<b>Welcome messages:</b> {state}\n"
        f"<i>Admins: /setwelcome on|off.</i>")


async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setwelcome") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg not in ("on", "off", "enable", "disable", "yes", "no"):
        await update.effective_message.reply_text("Usage: /setwelcome on|off")
        return
    enabled = arg in ("on", "enable", "yes")
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        await SettingsRepository(session).update(g.id, welcome_enabled=enabled)
        await session.commit()
    await update.effective_message.reply_text(
        f"Welcome messages {'enabled' if enabled else 'disabled'}.")


async def goodbye_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "goodbye") is None:
        return
    chat = update.effective_chat
    _, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    state = "<b>On</b>" if s["goodbye_enabled"] else "<b>Off</b>"
    await update.effective_message.reply_html(
        f"<b>Goodbye messages:</b> {state}\n"
        f"<i>Admins: /setgoodbye on|off.</i>")


async def setgoodbye_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setgoodbye") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg not in ("on", "off", "enable", "disable", "yes", "no"):
        await update.effective_message.reply_text("Usage: /setgoodbye on|off")
        return
    enabled = arg in ("on", "enable", "yes")
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        await SettingsRepository(session).update(g.id, goodbye_enabled=enabled)
        await session.commit()
    await update.effective_message.reply_text(
        f"Goodbye messages {'enabled' if enabled else 'disabled'}.")


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "rules") is None:
        return
    chat = update.effective_chat
    _, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    if not s["rules"]:
        await update.effective_message.reply_text("No rules have been set. Administrators can add them with /setrules <text>.")
        return
    await update.effective_message.reply_html(f"<b>Group Rules</b>\n\n{html.escape(s['rules'])}")


async def setrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setrules") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    text = " ".join(context.args or []).strip()
    if not text and update.effective_message.reply_to_message and update.effective_message.reply_to_message.text:
        text = update.effective_message.reply_to_message.text.strip()
    if not text:
        await update.effective_message.reply_text("Usage: /setrules <text> (or reply with /setrules)")
        return
    if text.lower() in ("clear", "off", "none", "delete"):
        text = None
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        await SettingsRepository(session).update(g.id, rules=text)
        await session.commit()
    await update.effective_message.reply_text("Rules cleared." if text is None else "Group rules updated.")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "settings") is None:
        return
    chat = update.effective_chat
    _, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    tick = lambda b: "On" if b else "Off"  # noqa: E731
    await update.effective_message.reply_html(
        f"<b>Group Settings</b>\n\n"
        f"Warn limit: <b>{s['warn_limit']}</b> <i>(/setwarnlimit N)</i>\n"
        f"Welcome: {tick(s['welcome_enabled'])}\n"
        f"Goodbye: {tick(s['goodbye_enabled'])}\n"
        f"Anti-flood: {tick(s['anti_flood_enabled'])}\n"
        f"Anti-spam: {tick(s['anti_spam_enabled'])}\n"
        f"Reports: {tick(s['reports_enabled'])}\n"
        f"Logging: {tick(s['log_enabled'])}\n"
        f"Rules: {'set' if s['rules'] else 'not set'}")


async def setwarnlimit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setwarnlimit") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /setwarnlimit <number 1-20>")
        return
    n = max(1, min(20, int(context.args[0])))
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        await SettingsRepository(session).update(g.id, warn_limit=n)
        await session.commit()
    await update.effective_message.reply_html(f"Warn limit set to <b>{n}</b>.")

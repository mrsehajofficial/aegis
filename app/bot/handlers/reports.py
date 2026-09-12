"""
reports.py — /report command for members to report messages to admins.
"""
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.settings import SettingsRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report a message to admins: /report [reason]"""
    if await guard(update, context, "report") is None:
        return
    chat = update.effective_chat
    msg = update.effective_message
    # Check if reports are enabled for this group
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            return
        settings = await SettingsRepository(session).get_by_group_id(g.id)
        if settings and not settings.reports_enabled:
            await msg.reply_html("<b>Reports are disabled in this group.</b>")
            return
        # Get all admins
        admins = await MemberRepository(session).list_admins(g.id)
    if not admins:
        await msg.reply_html("<b>No admins to report to.</b>")
        return
    # Get the message being reported
    target_msg = msg.reply_to_message
    if not target_msg:
        await msg.reply_html("<b>Reply to a message to report it.</b>")
        return
    # Dont allow reporting bot messages or own messages
    if target_msg.from_user.is_bot:
        await msg.reply_html("<b>Cannot report bot messages.</b>")
        return
    reporter = msg.from_user
    reported = target_msg.from_user
    reason = " ".join(context.args) if context.args else "No reason provided"
    # Build report
    report_text = (
        f"<b>Report</b>\n\n"
        f"<b>Reported user:</b> {html.escape(reported.full_name)} (<code>{reported.id}</code>)\n"
        f"<b>Reported by:</b> {html.escape(reporter.full_name)} (<code>{reporter.id}</code>)\n"
        f"<b>Reason:</b> {html.escape(reason)}\n\n"
        f"<a href=\"tg://user?id={reported.id}\">View user</a>"
    )
    # Forward the reported message to each admin
    sent_count = 0
    for admin in admins:
        try:
            await context.bot.forward_message(
                chat_id=admin.telegram_id,
                from_chat_id=chat.id,
                message_id=target_msg.message_id
            )
            await context.bot.send_message(
                chat_id=admin.telegram_id,
                text=report_text,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception as e:
            logger.debug(f"Could not send report to admin {admin.telegram_id}: {e}")
    if sent_count > 0:
        await msg.reply_html(f"<b>Reported to {sent_count} admin(s).</b>")
    else:
        await msg.reply_html("<b>Could not notify any admins.</b>")


async def setreports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle reports: /reports on|off"""
    if await guard(update, context, "reports") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    args = context.args or []
    if not args or args[0].lower() not in ("on", "off", "enable", "disable", "yes", "no"):
        await update.effective_message.reply_text("Usage: /reports on|off")
        return
    enabled = args[0].lower() in ("on", "enable", "yes")
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if g:
            await SettingsRepository(session).update(g.id, reports_enabled=enabled)
            await session.commit()
    if enabled:
        await update.effective_message.reply_html("<b>Reports enabled.</b>\nMembers can now use /report.")
    else:
        await update.effective_message.reply_html("<b>Reports disabled.</b>")

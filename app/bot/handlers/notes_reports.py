"""
notes.py — Admin notes (saved text snippets) and /report command.
"""
import html
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.protection import NoteRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)


async def save_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save a note: /save <keyword> <content...>"""
    if await guard(update, context, "save") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nAdministrators only.")
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /save <keyword> <content...>")
        return
    keyword = args[0].strip()
    content = " ".join(args[1:])
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        await NoteRepository(session).save_note(g.id, keyword, content)
        await session.commit()
    await update.effective_message.reply_html(
        f"<b>Note saved.</b>\nKeyword: <code>{html.escape(keyword)}</code>\n"
        f"<i>Use #{html.escape(keyword)} in chat to recall it.</i>")


async def get_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get a note: #<keyword>"""
    if not update.effective_message or not context.args:
        return
    chat = update.effective_chat
    keyword = context.args[0].lstrip("#").strip()
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            return
        note = await NoteRepository(session).get_note(g.id, keyword)
        if note and note.content:
            await update.effective_message.reply_html(note.content)
        else:
            await update.effective_message.reply_text(f"Note '{html.escape(keyword)}' not found.")


async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all notes in this group."""
    if await guard(update, context, "notes") is None:
        return
    chat = update.effective_chat
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        notes = await NoteRepository(session).get_by_group(g.id)
    if not notes:
        await update.effective_message.reply_html("<b>Notes</b>\n\nNo notes saved in this group.")
        return
    lines = ["<b>Saved Notes</b>\n"]
    for note in notes:
        lines.append(f"• <code>#{html.escape(note.keyword)}</code>")
    lines.append("\n<i>Use /save <keyword> <content> to save, #keyword to recall</i>")
    await update.effective_message.reply_html("\n".join(lines))


async def clear_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a note: /clear <keyword>"""
    if await guard(update, context, "clear") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nAdministrators only.")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /clear <keyword>")
        return
    keyword = context.args[0].strip()
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        removed = await NoteRepository(session).remove_note(g.id, keyword)
        await session.commit()
    if removed:
        await update.effective_message.reply_html(f"<b>Note removed:</b> <code>{html.escape(keyword)}</code>")
    else:
        await update.effective_message.reply_text(f"Note '{html.escape(keyword)}' not found.")


# ── Reports ──────────────────────────────────────────────────────────────────
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report a message to admins: /report [reply]"""
    if await guard(update, context, "report") is None:
        return
    chat = update.effective_chat
    message = update.effective_message
    reported_msg = None
    if message.reply_to_message:
        reported_msg = message.reply_to_message
    if not reported_msg:
        await update.effective_message.reply_text("Usage: Reply to a message with /report to notify admins.")
        return
    try:
        admins = await chat.get_administrators()
        admin_mentions = []
        for admin in admins:
            if not admin.user.is_bot and admin.user.id != reported_msg.from_user.id:
                admin_mentions.append(
                    f'<a href="tg://user?id={admin.user.id}">{html.escape(admin.user.first_name)}</a>')
        report_text = (
            f"<b>Report</b>\n\n"
            f"<b>Reported user:</b> <a href=\"tg://user?id={reported_msg.from_user.id}\">"
            f"{html.escape(reported_msg.from_user.first_name)}</a>\n"
            f"<b>Message:</b> <i>{html.escape((reported_msg.text or '')[:200])}</i>\n\n"
            f"<b>Admins notified:</b> {', '.join(admin_mentions) if admin_mentions else 'none'}")
        await update.effective_message.reply_html(report_text, reply_to_message_id=reported_msg.message_id)
    except Exception as e:
        await update.effective_message.reply_text(f"Report failed: {e}")


async def setreports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle reports: /setreports on|off"""
    if await guard(update, context, "setreports") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nAdministrators only.")
        return
    args = context.args or []
    if not args or args[0].lower() not in ("on", "off", "enable", "disable", "yes", "no"):
        await update.effective_message.reply_text("Usage: /setreports on|off")
        return
    enabled = args[0].lower() in ("on", "enable", "yes")
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        await SettingsRepository(session).update(g.id, reports_enabled=enabled)
        await session.commit()
    await update.effective_message.reply_html(f"<b>Reports {'enabled' if enabled else 'disabled'}.</b>")


# ── Reports ──────────────────────────────────────────────────────────────────
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report a message to admins: /report [reply]"""
    if await guard(update, context, "report") is None:
        return
    chat = update.effective_chat
    message = update.effective_message
    reported_msg = None
    if message.reply_to_message:
        reported_msg = message.reply_to_message
    if not reported_msg:
        await update.effective_message.reply_text("Usage: Reply to a message with /report to notify admins.")
        return
    try:
        admins = await chat.get_administrators()
        admin_mentions = []
        for admin in admins:
            if not admin.user.is_bot and admin.user.id != reported_msg.from_user.id:
                admin_mentions.append(
                    f'<a href="tg://user?id={admin.user.id}">{html.escape(admin.user.first_name)}</a>')
        report_text = (
            f"<b>Report</b>\n\n"
            f"<b>Reported user:</b> <a href=\"tg://user?id={reported_msg.from_user.id}\">"
            f"{html.escape(reported_msg.from_user.first_name)}</a>\n"
            f"<b>Message:</b> <i>{html.escape((reported_msg.text or '')[:200])}</i>\n\n"
            f"<b>Admins notified:</b> {', '.join(admin_mentions) if admin_mentions else 'none'}")
        await update.effective_message.reply_html(report_text, reply_to_message_id=reported_msg.message_id)
    except Exception as e:
        await update.effective_message.reply_text(f"Report failed: {e}")

async def clear_notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove all notes: /clearall"""
    if await guard(update, context, "clearall") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nAdministrators only.")
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        count = await NoteRepository(session).clear_group(g.id)
        await session.commit()
    await update.effective_message.reply_html(f"<b>Cleared {count} notes.</b>")
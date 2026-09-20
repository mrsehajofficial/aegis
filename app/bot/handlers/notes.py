"""
notes.py — Admin notes system for saving and retrieving snippets.
"""
import html
import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.protection import NoteRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)
# Regex to match #keyword in messages
NOTE_PATTERN = re.compile(r"#(\w+)")


async def save_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save a note: /save <keyword> <content>"""
    if await guard(update, context, "save") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /save <keyword> <content>")
        return
    keyword = args[0].strip().lower()
    content = " ".join(args[1:])
    if keyword.startswith("#"):
        keyword = keyword[1:]
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        await NoteRepository(session).save_note(g.id, keyword, content)
        await session.commit()
    await update.effective_message.reply_html(
        f"<b>Note saved.</b>\n\nUse <code>#{html.escape(keyword)}</code> to retrieve it."
    )


async def get_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get a note: /get <keyword>"""
    if await guard(update, context, "get") is None:
        return
    chat = update.effective_chat
    args = context.args or []
    keyword = None
    if args:
        keyword = args[0].strip().lower().lstrip("#")
    else:
        # Check if replying to a message with #keyword
        reply = update.effective_message.reply_to_message
        if reply and reply.text:
            match = NOTE_PATTERN.search(reply.text)
            if match:
                keyword = match.group(1).lower()
    if not keyword:
        await update.effective_message.reply_text("Usage: /get <keyword>")
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        note = await NoteRepository(session).get_note(g.id, keyword)
    if note and note.content:
        await update.effective_message.reply_html(note.content)
    else:
        await update.effective_message.reply_text(f"No note found for <code>{html.escape(keyword)}</code>.")


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
    lines = ["<b>Notes</b>\n"]
    for n in notes:
        preview = (n.content[:50] + "...") if n.content and len(n.content) > 50 else (n.content or "")
        lines.append(f"• <code>#{html.escape(n.keyword)}</code> — {html.escape(preview)}")
    await update.effective_message.reply_html("\n".join(lines))


async def clear_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a note: /clear <keyword>"""
    if await guard(update, context, "clear") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /clear <keyword>")
        return
    keyword = context.args[0].strip().lower().lstrip("#")
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered.")
            return
        removed = await NoteRepository(session).remove_note(g.id, keyword)
        await session.commit()
    if removed:
        await update.effective_message.reply_html(f"<b>Note removed:</b> <code>#{html.escape(keyword)}</code>")
    else:
        await update.effective_message.reply_text(f"No note found for <code>#{html.escape(keyword)}</code>.")


async def check_notes_in_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if a message contains #keyword and reply with the note."""
    message = update.effective_message
    if not message or not message.text:
        return
    chat = update.effective_chat
    if not chat:
        return
    match = NOTE_PATTERN.search(message.text)
    if not match:
        return
    keyword = match.group(1).lower()
    # Dont trigger on commands
    if message.text.startswith("/"):
        return
    try:
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                return
            note = await NoteRepository(session).get_note(g.id, keyword)
        if note and note.content:
            await message.reply_html(note.content)
    except Exception as e:
        logger.debug(f"Note check error in chat {chat.id}: {e}")

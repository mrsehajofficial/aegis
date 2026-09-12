"""
filters.py — Yuki keyword auto-reply filters.
"""
import html
import logging

from sqlalchemy import select
from telegram import Update, Chat
from telegram.ext import ContextTypes

from app.database.base import utc_now
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.models.filter import Filter
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


async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add/update a filter: /filter <keyword> <response...>"""
    if await guard(update, context, "filter") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text("Usage: /filter <keyword> <response text>")
        return
    keyword = context.args[0].lower().strip()
    response = " ".join(context.args[1:]).strip()
    if len(keyword) > 200 or len(response) > 3000:
        await update.effective_message.reply_text("Keyword or response exceeds the allowed length (keyword 200, response 3000 characters).")
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        q = await session.execute(select(Filter).where(Filter.group_id == g.id, Filter.trigger == keyword))
        f = q.scalar_one_or_none()
        if f is None:
            f = Filter(group_id=g.id, trigger=keyword, response=response, created_at=utc_now())
            session.add(f)
        else:
            f.response = response
            f.enabled = True
        await session.commit()
    await update.effective_message.reply_html(
        f"Filter <code>{html.escape(keyword)}</code> saved — it will now auto-reply in this group.")


async def filters_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "filters") is None:
        return
    chat = update.effective_chat
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        q = await session.execute(
            select(Filter).where(Filter.group_id == g.id, Filter.enabled == True).order_by(Filter.trigger))  # noqa: E712
        rows = q.scalars().all()
    if not rows:
        await update.effective_message.reply_text("No filters in this group. Add one with /filter <keyword> <response>.")
        return
    lines = ["<b>Active Filters</b>\n"]
    lines += [f"• <code>{html.escape(f.trigger)}</code>" for f in rows]
    await update.effective_message.reply_html("\n".join(lines))


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "stop") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /stop <keyword>")
        return
    keyword = context.args[0].lower().strip()
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        q = await session.execute(select(Filter).where(Filter.group_id == g.id, Filter.trigger == keyword))
        f = q.scalar_one_or_none()
        if not f:
            await update.effective_message.reply_text(f"No filter named <code>{html.escape(keyword)}</code>.",)
            return
        await session.delete(f)
        await session.commit()
    await update.effective_message.reply_html(f"Filter <code>{html.escape(keyword)}</code> removed.")


async def check_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Message handler: reply when a message matches a filter trigger (word match, case-insensitive)."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return
    text = (msg.text or "").strip().lower()
    if not text or text.startswith("/"):
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            return
        q = await session.execute(
            select(Filter).where(Filter.group_id == g.id, Filter.enabled == True))  # noqa: E712
        rows = q.scalars().all()
    for f in rows:
        trig = (f.trigger or "").lower()
        if trig and trig in text:
            try:
                await msg.reply_html(html.escape(f.response or ""), do_quote=False)
            except Exception:
                pass
            break

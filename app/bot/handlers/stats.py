"""
stats.py — /stats: a one-screen health report for the group.

Every number comes from existing database state (members cache, warnings,
audit log), so there is nothing new to collect: the bot has been recording
this data all along and Rose gives admins no way to see any of it.

`build_stats_text` is a pure function over a plain dict so the formatting is
unit-testable without a database.
"""
import html
import logging
import time
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.warnings import WarningRepository
from app.database.repositories.audit_logs import AuditLogRepository
from app.bot.helpers.ensure_group import guard
from app.bot.handlers.commands import _STARTED_AT as _CMD_STARTED_AT

logger = logging.getLogger(__name__)

# _STARTED_AT lives in commands.py (set at import time).
# mark_started() is kept as a no-op so application.py doesn't need changes.
_STARTED_AT: Optional[float] = None


def mark_started() -> None:
    """No-op kept for backwards compatibility — start time is tracked in commands.py."""
    pass


def format_uptime(seconds: float) -> str:
    """Compact uptime: 3d 4h, 2h 15m, 5m 30s, 42s."""
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def uptime_seconds() -> float:
    """Seconds since bot process start (sourced from commands._STARTED_AT)."""
    return time.monotonic() - _CMD_STARTED_AT


def build_stats_text(snapshot: dict) -> str:
    """Render the /stats panel body from pre-fetched values."""
    lines = [
        f"<b>Group Stats — {html.escape(snapshot['title'])}</b>",
        "",
        f"👥 Tracked members: <b>{snapshot['members']}</b>",
        f"🛡 Admins/owner: <b>{snapshot['admins']}</b>",
        f"⚠️ Warnings: <b>{snapshot['warnings']}</b> "
        f"across <b>{snapshot['warned_users']}</b> user(s)",
        f"🧾 Moderation actions logged: <b>{snapshot['actions']}</b>",
    ]
    top = snapshot.get("top_actions") or []
    if top:
        pretty = ", ".join(
            f"<code>{name}</code> ×{count}" for name, count in top[:5]
        )
        lines.append(f"Top actions: {pretty}")
    lines.append("")
    lines.append(f"🤖 Bot uptime: <b>{format_uptime(snapshot['uptime'])}</b>")
    return "\n".join(lines)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats — members, warnings, moderation volume and uptime."""
    if await guard(update, context, "stats") is None:
        return
    chat = update.effective_chat

    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text(
                "Group is not registered yet. Please try again in a moment."
            )
            return
        member_repo = MemberRepository(session)
        warning_repo = WarningRepository(session)
        audit_repo = AuditLogRepository(session)

        members = await member_repo.count_members(g.id)
        admins = await member_repo.count_admins(g.id)
        total_warnings, warned_users = await warning_repo.count_for_group(g.id)
        total_actions = await audit_repo.count_for_group(g.id)
        top_actions = await audit_repo.action_counts(g.id)
        title = g.title or chat.title or "this group"

    snapshot = {
        "title": title,
        "members": members,
        "admins": admins,
        "warnings": total_warnings,
        "warned_users": warned_users,
        "actions": total_actions,
        "top_actions": top_actions,
        "uptime": uptime_seconds(),
    }
    await update.effective_message.reply_html(build_stats_text(snapshot))
    logger.debug(
        f"/stats served for chat {chat.id} ({settings.BOT_NAME}, uptime={snapshot['uptime']:.0f}s)"
    )
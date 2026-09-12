"""
moderation.py — Yuki moderation commands (ban, mute, warn, pin...).
"""
import html
import logging
import re
from datetime import timedelta
from typing import Optional, Tuple

from telegram import Update, Chat, ChatPermissions
from telegram.ext import ContextTypes

from app.bot.helpers.resolve import resolve_user

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.settings import SettingsRepository
from app.database.repositories.audit_logs import AuditLogRepository
from app.moderation.warning_service import issue_warning, get_user_warnings, reset_user_warnings
from app.bot.middleware.auth import get_calling_user_role, role_rank, is_admin_or_above, is_super_admin
from app.bot.helpers.ensure_group import guard

logger = logging.getLogger(__name__)
BOT_NAME = settings.BOT_NAME


async def _require_group(update: Update) -> Optional[Chat]:
    chat = update.effective_chat
    if chat is None or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        if update.effective_message:
            await update.effective_message.reply_text("This command only works in groups.")
        return None
    return chat


async def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return None, ""
    if msg.reply_to_message and msg.reply_to_message.from_user:
        args = list(context.args or [])
        if args and args[0].startswith("@"):
            args = args[1:]
        return msg.reply_to_message.from_user, " ".join(args).strip()
    if context.args:
        first = context.args[0]
        lookup = None
        if first.startswith("@"):
            lookup = first
        elif first.isdigit():
            lookup = int(first)
        if lookup is not None:
            u = await resolve_user(context, chat.id, lookup)
            if u is not None:
                return u, " ".join(context.args[1:]).strip()
            return None, ""
    return None, ""


def _parse_duration(text: str) -> Optional[timedelta]:
    if not text:
        return None
    text = text.strip().lower()
    # Bare number means minutes: "/mute @user 10" == 10 minutes
    if text.isdigit():
        return timedelta(minutes=int(text))
    # Unit suffixes, optionally combined: 90s, 10m, 1h30m, 1d12h, 2w
    if not re.fullmatch(r"\d+[smhdw](?:\d+[smhdw])*", text):
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total_seconds = 0
    for n, unit in re.findall(r"(\d+)([smhdw])", text):
        total_seconds += int(n) * units[unit]
    return timedelta(seconds=total_seconds)


def _resolve_failure_hint(update: Update, context: ContextTypes.DEFAULT_TYPE, usage: str) -> str:
    """Build a helpful message when the target user couldn't be resolved."""
    msg = update.effective_message
    if msg.reply_to_message is None and context.args:
        return (
            f"Couldn't resolve {context.args[0]}. Telegram doesn't let bots look up "
            "people by username until they've sent a message here — ask them to send "
            "anything in this group once (or reply to one of their messages), then retry.\n\n"
            f"Usage: {usage}"
        )
    return f"Usage: {usage}"


async def _check_hierarchy(update: Update, target_id: int):
    caller_role = await get_calling_user_role(update)
    if role_rank(caller_role) < role_rank("admin"):
        return False, caller_role
    # Super admins outrank everyone except other super admins
    if is_super_admin(update.effective_user.id) and not is_super_admin(target_id):
        return True, caller_role
    chat = update.effective_chat
    target_role = "member"
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if g:
            mem = await MemberRepository(session).get_member(g.id, target_id)
            if mem:
                target_role = mem.role
    if is_super_admin(target_id):
        return False, caller_role
    if target_role in ("admin", "owner", "moderator") and role_rank(caller_role) <= role_rank(target_role):
        return False, caller_role
    return True, caller_role


async def _audit(action: str, chat_id: int, actor: int, target: Optional[int],
                reason: Optional[str], meta: Optional[dict] = None):
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat_id)
        await AuditLogRepository(session).log_event(
            action=action, group_id=g.id if g else None,
            actor_id=actor, target_id=target, reason=reason, metadata=meta or {})
        await session.commit()


def _mention(user) -> str:
    name = html.escape(user.first_name or "User")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "ban") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, reason = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/ban [reply|@user|id] [reason]"))
        return
    if target.id == context.bot.id:
        await update.effective_message.reply_text("I cannot ban myself.")
        return
    ok, _ = await _check_hierarchy(update, target.id)
    if not ok:
        await update.effective_message.reply_text("You cannot ban a member with an equal or higher rank.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, target.id)
    except Exception as e:
        await update.effective_message.reply_text(f"Ban failed. Make sure I am an administrator with ban rights.\n({e})")
        return
    await _audit("USER_BANNED", chat.id, update.effective_user.id, target.id, reason or None, {})
    await update.effective_message.reply_html(
        f"<b>{_mention(target)} has been banned</b>."
        + (f"\n<i>Reason: {html.escape(reason)}</i>" if reason else ""))


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "unban") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, _ = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/unban [reply|@user|id]"))
        return
    try:
        await context.bot.unban_chat_member(chat.id, target.id, only_if_banned=True)
    except Exception as e:
        await update.effective_message.reply_text(f"Unban failed. ({e})")
        return
    await _audit("USER_UNBANNED", chat.id, update.effective_user.id, target.id, None, {})
    await update.effective_message.reply_html(f"<b>{_mention(target)} has been unbanned</b>.")


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "kick") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, reason = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/kick [reply|@user|id] [reason]"))
        return
    ok, _ = await _check_hierarchy(update, target.id)
    if not ok:
        await update.effective_message.reply_text("You cannot kick a member with an equal or higher rank.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await context.bot.unban_chat_member(chat.id, target.id)
    except Exception as e:
        await update.effective_message.reply_text(f"Kick failed. Make sure I am an administrator with ban rights.\n({e})")
        return
    await _audit("USER_KICKED", chat.id, update.effective_user.id, target.id, reason or None, {})
    await update.effective_message.reply_html(
        f"<b>{_mention(target)} has been kicked</b>."
        + (f"\n<i>Reason: {html.escape(reason)}</i>" if reason else ""))


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "mute") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, rest = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/mute [reply|@user|id] [time e.g. 10m] [reason]"))
        return
    ok, _ = await _check_hierarchy(update, target.id)
    if not ok:
        await update.effective_message.reply_text("You cannot mute a member with an equal or higher rank.")
        return
    until = None
    reason = rest
    if rest:
        first, _, tail = rest.partition(" ")
        dur = _parse_duration(first)
        if dur:
            from datetime import datetime, timezone
            until = datetime.now(timezone.utc) + dur
            reason = tail.strip()
    try:
        await context.bot.restrict_chat_member(
            chat.id, target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until)
    except Exception as e:
        await update.effective_message.reply_text(f"Mute failed. Make sure I am an administrator with restrict rights.\n({e})")
        return
    await _audit("USER_MUTED", chat.id, update.effective_user.id, target.id, reason or None,
                 {"until": until.isoformat() if until else "forever"})
    label = f"muted until {until:%Y-%m-%d %H:%M} UTC" if until else "muted indefinitely"
    await update.effective_message.reply_html(
        f"<b>{_mention(target)} has been {label}</b>."
        + (f"\n<i>Reason: {html.escape(reason)}</i>" if reason else ""))


async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "unmute") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, _ = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/unmute [reply|@user|id]"))
        return
    ok, _ = await _check_hierarchy(update, target.id)
    if not ok:
        await update.effective_message.reply_text("You cannot unmute a member with an equal or higher rank.")
        return
    try:
        await context.bot.restrict_chat_member(
            chat.id, target.id,
            permissions=ChatPermissions.all_permissions())
    except Exception as e:
        await update.effective_message.reply_text(f"Unmute failed. Make sure I am an administrator with restrict rights.\n({e})")
        return
    await _audit("USER_UNMUTED", chat.id, update.effective_user.id, target.id, None, {})
    await update.effective_message.reply_html(f"<b>{_mention(target)} has been unmuted</b>.")


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "warn") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, reason = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/warn [reply|@user|id] [reason]"))
        return
    if target.is_bot:
        await update.effective_message.reply_text("Bots cannot be warned.")
        return
    try:
        total = await issue_warning(chat, update.effective_user, target, reason or None)
    except ValueError as e:
        await update.effective_message.reply_text(str(e))
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        limit = (await SettingsRepository(session).get_or_create(g.id)).warn_limit if g else 3
    msg = (f"<b>{_mention(target)} was warned</b> (<b>{total}/{limit}</b>)."
           + (f"\n<i>Reason: {html.escape(reason)}</i>" if reason else ""))
    if total >= limit:
        action = (settings.WARN_ACTION or "mute").lower()
        try:
            if action == "ban":
                await context.bot.ban_chat_member(chat.id, target.id)
                msg += "\nWarn limit reached — <b>banned</b>."
            elif action == "kick":
                await context.bot.ban_chat_member(chat.id, target.id)
                await context.bot.unban_chat_member(chat.id, target.id)
                msg += "\nWarn limit reached — <b>kicked</b>."
            else:
                await context.bot.restrict_chat_member(
                    chat.id, target.id, permissions=ChatPermissions(can_send_messages=False))
                msg += "\nWarn limit reached — <b>muted</b>."
            await _audit("WARN_LIMIT_ACTION", chat.id, context.bot.id, target.id, f"limit {limit}", {"action": action})
        except Exception as e:
            msg += f"\nLimit action failed: {html.escape(str(e))}"
    await update.effective_message.reply_html(msg)


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "warnings") is None:
        return
    chat = update.effective_chat
    target, _ = await _resolve_target(update, context)
    if target is None:
        target = update.effective_user
    warns = await get_user_warnings(chat, target)
    if not warns:
        await update.effective_message.reply_html(f"{_mention(target)} has a clean record — no warnings.")
        return
    lines = [f"<b>Warnings — {_mention(target)}</b> ({len(warns)})\n"]
    for i, w in enumerate(warns[:10], 1):
        r = html.escape(w.get("reason") or "No reason")
        lines.append(f"{i}. {r} <i>({(w.get('created_at') or '')[:10]})</i>")
    if len(warns) > 10:
        lines.append(f"<i>...and {len(warns)-10} more</i>")
    await update.effective_message.reply_html("\n".join(lines))


async def resetwarns_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "resetwarns") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    target, _ = await _resolve_target(update, context)
    if target is None:
        await update.effective_message.reply_text(
            _resolve_failure_hint(update, context, "/resetwarns [reply|@user|id]"))
        return
    try:
        n = await reset_user_warnings(chat, target, update.effective_user)
    except ValueError as e:
        await update.effective_message.reply_text(str(e))
        return
    await update.effective_message.reply_html(f"Cleared <b>{n}</b> warnings for {_mention(target)}.")


async def purge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "purge") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Usage: reply to a message with /purge to delete everything from there onward.")
        return
    start_id = msg.reply_to_message.message_id
    end_id = msg.message_id
    deleted = 0
    for mid in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(chat.id, mid)
            deleted += 1
        except Exception:
            continue
    await _audit("PURGE", chat.id, update.effective_user.id, None, None, {"deleted": deleted})
    # The purge range includes the command message itself, so a plain
    # send_message is used — reply_text would fail with
    # "Message to be replied not found".
    note = await context.bot.send_message(chat.id, f"Purged {deleted} messages.")
    try:
        import asyncio
        await asyncio.sleep(5)
        await note.delete()
    except Exception:
        pass


async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "pin") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Usage: reply to a message with /pin.")
        return
    silent = True
    if context.args and context.args[0].lower() in ("loud", "notify", "alert"):
        silent = False
    try:
        await context.bot.pin_chat_message(chat.id, msg.reply_to_message.message_id, disable_notification=silent)
    except Exception as e:
        await msg.reply_text(f"Pin failed. Make sure I am an administrator with pin rights.\n({e})")
        return
    await _audit("PINNED", chat.id, update.effective_user.id, None, None, {"message_id": msg.reply_to_message.message_id})
    await msg.reply_text("Message pinned.")


async def unpin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "unpin") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    try:
        await context.bot.unpin_chat_message(chat.id)
    except Exception as e:
        await update.effective_message.reply_text(f"Unpin failed. ({e})")
        return
    await _audit("UNPINNED", chat.id, update.effective_user.id, None, None, {})
    await update.effective_message.reply_text("Message unpinned.")


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /logs — recent audit log entries for this group (admins only)."""
    if await guard(update, context, "logs") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        rows = await AuditLogRepository(session).get_recent_logs(group_id=g.id, limit=10)
    if not rows:
        await update.effective_message.reply_text("No audit entries yet.")
        return
    lines = ["<b>Recent Actions</b>\n"]
    for r in rows:
        ts = r.created_at.strftime("%m-%d %H:%M") if r.created_at else "?"
        tgt = f" → <code>{r.target_id}</code>" if r.target_id else ""
        reason = f" — {html.escape(r.reason)}" if r.reason else ""
        lines.append(f"• <code>{html.escape(r.action)}</code> by <code>{r.actor_id}</code>{tgt}{reason} <i>({ts})</i>")
    await update.effective_message.reply_html("\n".join(lines))

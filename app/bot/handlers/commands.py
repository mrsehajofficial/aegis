import logging
import time
from typing import Optional

from sqlalchemy import text
from telegram import Update, Chat
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.bot.helpers.ensure_group import guard
from app.bot.helpers.resolve import resolve_user

logger = logging.getLogger(__name__)

# Process start marker — /ping reports uptime against this. Set at import time,
# which is effectively bot boot: main.py imports this module while building app.
_STARTED_AT = time.monotonic()

# Latency thresholds in milliseconds for the 🟢/🟡/🔴 indicator in /ping.
_LATENCY_GOOD_MS = 300.0
_LATENCY_OK_MS = 1000.0

# Icons are declared as codepoint escapes so they survive any editor or
# encoding round-trip: ping, green circle, yellow circle, red circle.
_PING_ICON = "\U0001F3D3"
_DOT_GOOD = "\U0001F7E2"
_DOT_OK = "\U0001F7E1"
_DOT_BAD = "\U0001F534"


def build_help_text() -> str:
    """Build the categorised command reference (shared by /help and the /start menu)."""
    return (
        f"<b>{settings.BOT_NAME} — Command Center</b>\n\n"

        "<b>Moderation</b> <i>(admins only)</i>\n"
        "/ban [reply|@user] [reason] — Ban a member\n"
        "/unban [reply|@user] — Remove a ban\n"
        "/kick [reply|@user] [reason] — Remove without ban\n"
        "/mute [reply|@user] [time] — Mute a member\n"
        "/unmute [reply|@user] — Remove a mute\n"
        "/warn [reply|@user] [reason] — Issue a warning\n"
        "/warnings [reply|@user] — View warnings\n"
        "/resetwarns [reply|@user] — Clear warnings\n"
        "/purge — Delete from the replied-to message onward\n"
        "/pin — Pin the replied-to message\n"
        "/unpin — Unpin the pinned message\n\n"

        "<b>Group</b> <i>(admins only)</i>\n"
        "/rules — Show the group rules\n"
        "/setrules [text] — Set the rules\n"
        "/welcome — Show the welcome message\n"
        "/setwelcome on|off|[text] — Toggle or set the welcome message\n"
        "/goodbye — Show the goodbye message\n"
        "/setgoodbye on|off|[text] — Toggle or set the goodbye message\n"
        "/settings — Group settings overview\n"
        "/setwarnlimit N — Warnings before action (1-20)\n\n"

        "<b>Protection</b> <i>(admins only)</i>\n"
        "/setantiflood on|off — Toggle anti-flood\n"
        "/setantispam on|off — Toggle anti-spam\n"
        "/setcaptcha on|off — Toggle the join captcha\n"
        "/lock [type] — Lock a content type\n"
        "/unlock [type] — Unlock a content type\n"
        "/locktypes — List available lock types\n"
        "/addblacklist [word] — Add a banned word\n"
        "/blacklist — List banned words\n"
        "/rmblacklist [word] — Remove a banned word\n\n"

        "<b>Notes</b> <i>(admins only)</i>\n"
        "/save [keyword] [content] — Save a note\n"
        "/get [keyword] — Retrieve a note\n"
        "/clear [keyword] — Remove a note\n"
        "/notes — List all notes\n\n"

        "<b>Filters</b> <i>(admins only)</i>\n"
        "/filter [keyword] [response] — Add an auto-reply filter\n"
        "/filters — List active filters\n"
        "/stop [keyword] — Remove a filter\n\n"

        "<b>Reports</b>\n"
        "/report — Report a message to admins (reply to message)\n"
        "/setreports on|off — Toggle reports (admins only)\n\n"

        "<b>Information</b>\n"
        "/ping — Bot latency, database and uptime\n"
        "/stats — Group health overview (admins only)\n"
        "/id — Show chat, user and message IDs\n"
        "/info [reply|@user|id] — User profile and role\n"
        "/admins — List group administrators\n\n"

        "<b>Admin</b> <i>(admins only)</i>\n"
        "/logs — Recent moderation log\n\n"

        "<i>Commands marked (admins only) require admin or owner role.</i>"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — display categorised command reference."""
    await update.message.reply_html(build_help_text())


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /id — return chat/user/message IDs."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or chat is None or user is None:
        return

    lines = [
        "<b>ID Information</b>\n",
        f"Your ID: <code>{user.id}</code>",
        f"Chat ID: <code>{chat.id}</code>",
        f"Chat type: {chat.type}",
    ]

    if message.reply_to_message:
        replied = message.reply_to_message
        replied_user = replied.from_user
        lines.append("")
        lines.append(f"Replied message ID: <code>{replied.message_id}</code>")
        if replied_user:
            lines.append(f"Replied user ID: <code>{replied_user.id}</code>")
            if replied_user.username:
                lines.append(f"Replied username: @{replied_user.username}")

    await message.reply_html("\n".join(lines))


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info — display user profile and group role."""
    message = update.effective_message
    chat = update.effective_chat

    if message is None or chat is None:
        return

    if chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        if await guard(update, context, "info") is None:
            return

    # Determine target user
    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif context.args:
        first = context.args[0]
        if first.startswith("@") or first.isdigit():
            target_user = await resolve_user(
                context, chat.id, int(first) if first.isdigit() else first
            )
    else:
        target_user = update.effective_user

    if target_user is None:
        await message.reply_text("User not found. Reply to one of their messages, or provide their @username or numeric ID.")
        return

    # Build display name
    full_name = target_user.first_name
    if target_user.last_name:
        full_name += f" {target_user.last_name}"

    mention = f'<a href="tg://user?id={target_user.id}">{full_name}</a>'

    lines = [
        "<b>User Information</b>\n",
        f"Name: {mention}",
        f"ID: <code>{target_user.id}</code>",
    ]

    if target_user.username:
        lines.append(f"Username: @{target_user.username}")

    lines.append(f"Bot: {'Yes' if target_user.is_bot else 'No'}")

    # Fetch role from DB if in a group
    if chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        async with get_session() as session:
            group_repo = GroupRepository(session)
            member_repo = MemberRepository(session)
            group = await group_repo.get_by_telegram_id(chat.id)
            if group:
                member = await member_repo.get_member(group.id, target_user.id)
                role = member.role if member else "member"
                lines.append(f"Role: {role.title()}")

    await message.reply_html("\n".join(lines))


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admins — list all administrators in the group."""
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    if chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        await message.reply_text("This command only works in groups.")
        return

    if await guard(update, context, "admins") is None:
        return

    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.error(f"Failed to get admins for chat {chat.id}: {e}")
        await message.reply_text("Could not fetch the admin list. Make sure I have the required permissions.")
        return

    lines = ["<b>Group Administrators</b>\n"]
    for admin in admins:
        user = admin.user
        if user.is_bot:
            continue
        full_name = user.first_name
        if user.last_name:
            full_name += f" {user.last_name}"
        mention = f'<a href="tg://user?id={user.id}">{full_name}</a>'
        role_label = "Owner" if admin.status == "creator" else "Admin"
        if user.username:
            lines.append(f"• <b>{role_label}</b>: {mention} (@{user.username})")
        else:
            lines.append(f"• <b>{role_label}</b>: {mention}")

    if len(lines) == 1:
        lines.append("No human admins found.")

    await message.reply_html("\n".join(lines))


def _latency_dot(ms: float) -> str:
    """Traffic-light indicator for a latency measurement in milliseconds."""
    if ms < _LATENCY_GOOD_MS:
        return _DOT_GOOD
    if ms < _LATENCY_OK_MS:
        return _DOT_OK
    return _DOT_BAD


def _format_uptime(seconds: float) -> str:
    """Render a duration in seconds as e.g. '2d 3h 14m'."""
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}m {secs}s"


async def build_ping_text(
    context: ContextTypes.DEFAULT_TYPE,
    reply_ms: Optional[float] = None,
) -> str:
    """
    Probe Telegram, the database and process uptime, and render an HTML report.

    Shared by /ping and the /start menu so both report identical numbers.
    """
    lines = [f"<b>{_PING_ICON} Pong</b>\n"]

    # Telegram API round-trip (a lightweight getMe — no chat traffic).
    start = time.perf_counter()
    try:
        await context.bot.get_me()
        api_ms = (time.perf_counter() - start) * 1000.0
        lines.append(f"{_latency_dot(api_ms)} Telegram API: <code>{api_ms:.0f} ms</code>")
    except Exception as e:
        logger.warning(f"Ping API probe failed: {e}")
        lines.append("⚠️ Telegram API: <code>unreachable</code>")

    # Database round-trip.
    try:
        start = time.perf_counter()
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        db_ms = (time.perf_counter() - start) * 1000.0
        lines.append(f"{_latency_dot(db_ms)} Database: <code>{db_ms:.0f} ms</code>")
    except Exception as e:
        logger.warning(f"Ping DB probe failed: {e}")
        lines.append("⚠️ Database: <code>unreachable</code>")

    if reply_ms is not None:
        lines.append(f"{_latency_dot(reply_ms)} Command round-trip: <code>{reply_ms:.0f} ms</code>")

    lines.append(f"🕒 Uptime: <code>{_format_uptime(time.monotonic() - _STARTED_AT)}</code>")
    return "\n".join(lines)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ping — measure API, database and command round-trip latency."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None:
        return
    # Cheap but not free (two network probes) — rate-limit inside groups.
    if chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        if await guard(update, context, "ping") is None:
            return

    start = time.perf_counter()
    sent = await message.reply_text(f"{_PING_ICON} Pinging…")
    reply_ms = (time.perf_counter() - start) * 1000.0

    await sent.edit_text(await build_ping_text(context, reply_ms=reply_ms), parse_mode="HTML")

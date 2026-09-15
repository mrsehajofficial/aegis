"""
captcha.py — Join-captcha: mute + challenge new members on join.

New members must prove they are human by tapping "I'm not a bot" within the
timeout, otherwise they are kicked (or banned, per group settings).

Design notes:
- Pure in-memory store keyed by (chat_id, user_id). Verification is transient
  state, not durable configuration: losing it on restart is benign (the member
  simply stays muted until an admin unmutes), and sharing it across workers
  would add a Redis dependency to something that defaults off.
- Expiry uses plain asyncio tasks rather than PTB's JobQueue: the installed
  dependency set has no APScheduler (JobQueue is None without it), and pending
  challenges are deliberately in-memory — a restart drops them anyway.
- Restriction is applied *before* the challenge is recorded. Enforcement has a
  safety valve: if kick/ban fails on expiry, the mute is lifted so the member
  is never stuck muted-and-present.
"""
import asyncio
import html
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from telegram import (
    Chat,
    ChatMember,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.audit_logs import AuditLogRepository
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)

# Callback prefix keeps captcha taps separate from the menu: and cfg: routers.
PREFIX = "captcha:"
VERIFY_DATA = f"{PREFIX}verify"

# Zero texting ability, but the member can still tap the verify button.
# Callback queries do not require send-message permission.
MUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

# Full restore for a verified member. Telegram applies group defaults on
# unrestrict, so passing all-True restores normal participation.
FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
    can_manage_topics=False,
)

# Statuses that count as "just joined".
_JOIN_STATUSES = ("member", "administrator", "restricted")


@dataclass
class PendingCaptcha:
    """One outstanding join challenge."""

    chat_id: int
    user_id: int
    expires_at: float
    message_id: Optional[int] = None


# {(chat_id, user_id): PendingCaptcha}
_pending: Dict[Tuple[int, int], PendingCaptcha] = {}

# {(chat_id, user_id): asyncio.Task} — cancelled when a member verifies early.
_expiry_tasks: Dict[Tuple[int, int], "asyncio.Task[None]"] = {}


def build_captcha_keyboard() -> InlineKeyboardMarkup:
    """Single verify button shown under the challenge message."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ I'm not a bot", callback_data=VERIFY_DATA)]]
    )


def build_captcha_text(user_mention: str, timeout_seconds: int) -> str:
    """Challenge copy — mention is pre-escaped HTML from the caller."""
    minutes = max(1, round(timeout_seconds / 60))
    return (
        f"👋 Welcome, {user_mention}!\n\n"
        f"Please verify you're human by tapping the button below "
        f"within <b>{minutes} minute(s)</b>.\n"
        f"<i>Unverified members are removed automatically.</i>"
    )


def get_pending(chat_id: int, user_id: int) -> Optional[PendingCaptcha]:
    """Return the outstanding challenge, dropping it if already expired."""
    pending = _pending.get((chat_id, user_id))
    if pending is None:
        return None
    if pending.expires_at <= time.monotonic():
        _pending.pop((chat_id, user_id), None)
        return None
    return pending


def clear_all() -> None:
    """Test hook: drop every pending challenge and expiry task."""
    _pending.clear()
    for task in _expiry_tasks.values():
        task.cancel()
    _expiry_tasks.clear()


def _is_new_join(old_status: str, new_status: str) -> bool:
    return old_status in ("left", "kicked") and new_status in _JOIN_STATUSES


async def load_captcha_settings(chat_id: int) -> Optional[Tuple[bool, int, str]]:
    """
    Read (enabled, timeout_seconds, action) for a group, or None when the
    group is not registered.
    """
    async with get_session() as session:
        group = await GroupRepository(session).get_by_telegram_id(chat_id)
        if group is None:
            return None
        stored = await SettingsRepository(session).get_by_group_id(group.id)
        if stored is None:
            return (False, 120, "kick")
        return (stored.captcha_enabled, stored.captcha_timeout_seconds, stored.captcha_action)


async def _log_captcha_event(chat_id: int, action: str, target_id: int) -> None:
    """Best-effort audit entry so /logs and /stats reflect captcha outcomes."""
    try:
        async with get_session() as session:
            group = await GroupRepository(session).get_by_telegram_id(chat_id)
            if group is None:
                return
            await AuditLogRepository(session).log_event(
                action=action, group_id=group.id, target_id=target_id
            )
            await session.commit()
    except Exception as e:
        logger.debug(f"Captcha audit log failed for chat {chat_id}: {e}")


async def handle_captcha_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ChatMemberHandler hook: mute + challenge every new human member when the
    captcha is enabled for the group. Admins, the bot itself and other bots
    are exempt.
    """
    cmu = update.chat_member
    if cmu is None:
        return
    chat = cmu.chat
    user = cmu.new_chat_member.user if cmu.new_chat_member else None
    if (
        chat is None
        or chat.type not in (Chat.GROUP, Chat.SUPERGROUP)
        or user is None
        or user.is_bot
        or not _is_new_join(
            cmu.old_chat_member.status if cmu.old_chat_member else "",
            cmu.new_chat_member.status if cmu.new_chat_member else "",
        )
    ):
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
            return
    except Exception as e:
        logger.debug(f"Could not check membership for captcha in {chat.id}: {e}")

    loaded = await load_captcha_settings(chat.id)
    if not loaded or not loaded[0]:
        return
    _, timeout_seconds, _action = loaded

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id, user_id=user.id, permissions=MUTED_PERMISSIONS
        )
    except Exception as e:
        # Without the mute the challenge is pointless — a spam bot can just talk.
        logger.warning(f"Could not mute {user.id} for captcha in {chat.id}: {e}")
        return

    mention = f"<a href=\"tg://user?id={user.id}\">{html.escape(user.full_name)}</a>"
    try:
        challenge = await context.bot.send_message(
            chat_id=chat.id,
            text=build_captcha_text(mention, timeout_seconds),
            parse_mode="HTML",
            reply_markup=build_captcha_keyboard(),
        )
        message_id: Optional[int] = challenge.message_id
    except Exception as e:
        logger.warning(f"Could not send captcha challenge in {chat.id}: {e}")
        message_id = None

    _pending[(chat.id, user.id)] = PendingCaptcha(
        chat_id=chat.id,
        user_id=user.id,
        expires_at=time.monotonic() + timeout_seconds,
        message_id=message_id,
    )
    _schedule_expiry(chat.id, user.id, timeout_seconds, context)


def _schedule_expiry(
    chat_id: int, user_id: int, delay_seconds: float, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Arm (or re-arm) the timeout task for one challenge."""
    old = _expiry_tasks.get((chat_id, user_id))
    if old is not None and not old.done():
        old.cancel()
    _expiry_tasks[(chat_id, user_id)] = asyncio.create_task(
        _expire_later(chat_id, user_id, delay_seconds, context)
    )


async def _expire_later(
    chat_id: int, user_id: int, delay_seconds: float, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Remove a member who never verified. Cancelled by an early verify."""
    await asyncio.sleep(delay_seconds)
    _pending.pop((chat_id, user_id), None)
    _expiry_tasks.pop((chat_id, user_id), None)

    settings_row = await load_captcha_settings(chat_id)
    action = settings_row[2] if settings_row else "kick"

    # Safety valve: whatever happens below, never leave the member muted and
    # present — if enforcement fails we un-mute on the way out.
    removed = False
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        removed = True
        if action != "ban":
            # "kick" = remove without a permanent ban.
            await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    except Exception as e:
        logger.warning(f"Captcha enforcement failed for {user_id} in {chat_id}: {e}")
    try:
        await context.bot.unrestrict_chat_member(
            chat_id, user_id, permissions=FULL_PERMISSIONS
        )
    except Exception:
        pass  # member already removed, or left — nothing to restore

    await _log_captcha_event(chat_id, "CAPTCHA_EXPIRED", user_id)
    label = "banned" if action == "ban" else "removed"
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🤖 <a href=\"tg://user?id={user_id}\">A member</a> did not verify "
                f"in time and was {label}."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.debug(f"Could not announce captcha expiry in {chat_id}: {e}")
    return removed


async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route taps on the "I'm not a bot" button (callback data ``captcha:verify``)."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    message = query.message
    user = query.from_user
    chat = message.chat if message is not None else update.effective_chat
    if chat is None or user is None or (query.data or "") != VERIFY_DATA:
        return

    pending = get_pending(chat.id, user.id)
    if pending is None:
        # Stale tap: already verified, expired, or from someone else's button.
        # Their own button still answers, so nothing else to do.
        return

    # Verified: drop the challenge and cancel the pending kick.
    _pending.pop((chat.id, user.id), None)
    task = _expiry_tasks.pop((chat.id, user.id), None)
    if task is not None and not task.done():
        task.cancel()

    try:
        await context.bot.unrestrict_chat_member(
            chat_id=chat.id, user_id=user.id, permissions=FULL_PERMISSIONS
        )
    except Exception as e:
        logger.warning(f"Could not unrestrict verified user {user.id} in {chat.id}: {e}")

    await _log_captcha_event(chat.id, "CAPTCHA_PASSED", user.id)

    # Remove the challenge message so the group stays clean.
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Could not delete captcha challenge in {chat.id}: {e}")


def _parse_captcha_args(args) -> Optional[Tuple[Optional[bool], Optional[int], Optional[str]]]:
    """Parse '/setcaptcha on|off [minutes] [kick|ban]' — None means 'not given'."""
    enabled: Optional[bool] = None
    minutes: Optional[int] = None
    action: Optional[str] = None
    rest = list(args)
    if rest and rest[0].lower() in ("on", "enable", "yes"):
        enabled = True
        rest = rest[1:]
    elif rest and rest[0].lower() in ("off", "disable", "no"):
        enabled = False
        rest = rest[1:]
    if rest and rest[0].isdigit():
        minutes = int(rest[0])
        rest = rest[1:]
    if rest and rest[0].lower() in ("kick", "ban"):
        action = rest[0].lower()
    if rest:  # unparsed leftovers mean bad syntax
        return None
    if enabled is None and minutes is None and action is None:
        return None
    return enabled, minutes, action


async def setcaptcha_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle/configure the join captcha: /setcaptcha on|off [minutes] [kick|ban]."""
    if await guard(update, context, "setcaptcha") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return

    parsed = _parse_captcha_args(context.args or [])
    if parsed is None:
        await update.effective_message.reply_text(
            "Usage: /setcaptcha on|off [minutes] [kick|ban]\n"
            "Example: /setcaptcha on 5 kick"
        )
        return
    enabled, minutes, action = parsed

    kwargs: dict = {}
    if enabled is not None:
        kwargs["captcha_enabled"] = enabled
    if minutes is not None:
        kwargs["captcha_timeout_seconds"] = max(1, min(60, minutes)) * 60
    if action is not None:
        kwargs["captcha_action"] = action

    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        stored = await SettingsRepository(session).update(g.id, **kwargs)
        await session.commit()
        state = stored.captcha_enabled
        timeout_min = max(1, stored.captcha_timeout_seconds // 60)
        punish = stored.captcha_action

    if state:
        await update.effective_message.reply_html(
            f"<b>Join captcha enabled.</b>\n"
            f"New members have <b>{timeout_min} minute(s)</b> to verify; "
            f"otherwise they are {punish}ed."
        )
    else:
        await update.effective_message.reply_html("<b>Join captcha disabled.</b>")

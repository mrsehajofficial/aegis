"""
settings_ui.py — /settings as a tappable control panel.

Configuring a group used to mean memorising flags ("/setwelcome on",
"/setantispam off"). This renders the same state as inline buttons, so an admin
can read the group's posture at a glance and change it in one tap.

Callback data is namespaced ``cfg:`` so it stays independent of the ``menu:``
router behind /start. Telegram caps callback data at 64 bytes, which is why the
field name is sent rather than a sentence.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.bot.helpers.ensure_group import guard
from app.bot.helpers.menus import render_menu
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)

# (field on GroupSettings, button label, one-line description)
TOGGLES = (
    ("welcome_enabled", "Welcome", "greet new members"),
    ("goodbye_enabled", "Goodbye", "announce members who leave"),
    ("anti_flood_enabled", "Anti-flood", "mute rapid-fire posters"),
    ("anti_spam_enabled", "Anti-spam", "delete spam, links and abuse"),
    ("captcha_enabled", "Join captcha", "verify new members with a button"),
    ("reports_enabled", "Reports", "let members report messages"),
    ("log_enabled", "Logging", "record moderation actions"),
)

_TOGGLE_KEYS = {key for key, _, _ in TOGGLES}

_ON = "\u2705"
_OFF = "\u274C"
_CLOSE_ICON = "\u2716\uFE0F"

_PREFIX = "cfg:"


async def _load_snapshot(chat_id: int):
    """
    Read the group's settings into a plain dict.

    Values are copied out inside the session because the ORM objects expire when
    it closes.
    """
    async with get_session() as session:
        group = await GroupRepository(session).get_by_telegram_id(chat_id)
        if group is None:
            return None
        stored = await SettingsRepository(session).get_or_create(group.id)
        snapshot = {key: bool(getattr(stored, key, False)) for key in _TOGGLE_KEYS}
        snapshot["warn_limit"] = stored.warn_limit
        snapshot["rules_set"] = bool(stored.rules)
        return snapshot


def build_settings_text(snapshot: dict) -> str:
    """Human-readable panel body."""
    lines = ["<b>Group Settings</b>", "<i>Tap a setting to toggle it.</i>", ""]
    for key, label, description in TOGGLES:
        mark = _ON if snapshot.get(key) else _OFF
        lines.append(f"{mark} <b>{label}</b> — {description}")
    lines.append("")
    lines.append(
        f"Warn limit: <b>{snapshot.get('warn_limit', 3)}</b> <i>(/setwarnlimit N)</i>"
    )
    lines.append(
        f"Rules: {'set' if snapshot.get('rules_set') else 'not set'} <i>(/setrules)</i>"
    )
    return "\n".join(lines)


def build_settings_keyboard(snapshot: dict) -> InlineKeyboardMarkup:
    """One row per toggle, plus a close button."""
    rows = [
        [
            InlineKeyboardButton(
                f"{_ON if snapshot.get(key) else _OFF} {label}",
                callback_data=f"{_PREFIX}toggle:{key}",
            )
        ]
        for key, label, _ in TOGGLES
    ]
    rows.append(
        [InlineKeyboardButton(f"{_CLOSE_ICON} Close", callback_data=f"{_PREFIX}close")]
    )
    return InlineKeyboardMarkup(rows)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings — render the group configuration as a control panel."""
    if await guard(update, context, "settings") is None:
        return
    chat = update.effective_chat
    snapshot = await _load_snapshot(chat.id)
    if snapshot is None:
        await update.effective_message.reply_text(
            "Group is not registered yet. Please try again in a moment."
        )
        return
    await update.effective_message.reply_html(
        build_settings_text(snapshot),
        reply_markup=build_settings_keyboard(snapshot),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle taps on the /settings panel (callback data prefix ``cfg:``)."""
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""

    if data == f"{_PREFIX}close":
        await query.answer()
        if query.message is not None:
            try:
                await query.message.delete()
            except Exception as e:
                logger.debug(f"Settings close failed: {e}")
        return

    # Every remaining action mutates group configuration.
    if not await is_admin_or_above(update, context):
        await query.answer("Only administrators can change settings.", show_alert=True)
        return

    key = data.split(":", 2)[-1]
    if key not in _TOGGLE_KEYS:
        await query.answer("Unknown setting.", show_alert=True)
        return

    chat = update.effective_chat
    if chat is None:
        await query.answer("This can only be changed in a group.", show_alert=True)
        return

    async with get_session() as session:
        group = await GroupRepository(session).get_by_telegram_id(chat.id)
        if group is None:
            await query.answer("This group is not registered yet.", show_alert=True)
            return
        repo = SettingsRepository(session)
        stored = await repo.get_or_create(group.id)
        new_value = not bool(getattr(stored, key, False))
        await repo.update(group.id, **{key: new_value})
        await session.commit()

    label = next(label for field, label, _ in TOGGLES if field == key)
    await query.answer(f"{label} {'enabled' if new_value else 'disabled'}.")

    # Re-render so the tick marks reflect the new state.
    snapshot = await _load_snapshot(chat.id)
    if snapshot is None:
        return
    await render_menu(
        query,
        context,
        build_settings_text(snapshot),
        build_settings_keyboard(snapshot),
    )
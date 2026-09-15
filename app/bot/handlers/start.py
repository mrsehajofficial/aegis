"""
start.py — /start onboarding and the inline menu behind it.

/start is the first thing most people ever send a bot, so it doubles as the
landing page: a one-screen pitch with tappable buttons instead of a wall of
command syntax. This module owns both the message and the CallbackQuery router
that serves every menu screen.
"""
import logging
from typing import Optional

from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.bot.handlers.commands import build_help_text, build_ping_text
from app.bot.helpers.menus import render_menu

logger = logging.getLogger(__name__)

_GROUP_TYPES = {Chat.GROUP, Chat.SUPERGROUP}

# Button icons are declared as codepoint escapes so they survive any editor or
# encoding round-trip: shield, book, ping-pong, plus, cross mark, back arrow.
_ICON_SHIELD = "\U0001F6E1\uFE0F"
_ICON_HELP = "\U0001F4D6"
_ICON_PING = "\U0001F3D3"
_ICON_ADD = "\U00002795"
# U+FE0F is the emoji-presentation selector: without it these two render as
# flat text glyphs instead of matching the colour icons above.
_ICON_CLOSE = "\U00002716\uFE0F"
_ICON_BACK = "\U000025C0\uFE0F"


def is_group_chat(update_or_message) -> bool:
    """True when an Update or Message belongs to a group/supergroup."""
    chat = getattr(update_or_message, "effective_chat", None)
    if chat is None:
        chat = getattr(update_or_message, "chat", None)
    return chat is not None and chat.type in _GROUP_TYPES


def build_start_text(is_group: bool) -> str:
    """Onboarding copy — shorter inside groups, where /start is rarely used."""
    if is_group:
        return (
            f"<b>{_ICON_SHIELD} {settings.BOT_NAME} is on duty.</b>\n\n"
            "I handle moderation, anti-spam, filters and member management.\n"
            "Tap <b>Commands</b> below for the full reference, or send /help.\n\n"
            "<i>Tip: promote me to admin to unlock every moderation action.</i>"
        )
    return (
        f"<b>{_ICON_SHIELD} {settings.BOT_NAME}</b>\n"
        "<i>Deterministic protection for your Telegram groups.</i>\n\n"
        "What I do:\n"
        "• <b>Moderation</b> — ban, mute, warn, purge\n"
        "• <b>Protection</b> — anti-flood, anti-spam, blacklists, locks\n"
        "• <b>Automation</b> — filters, notes, welcome &amp; goodbye\n"
        "• <b>Accountability</b> — every action logged and reviewable\n\n"
        "Tap <b>Commands</b> for the full reference, or add me to a group to begin."
    )


def build_menu(
    is_group: bool,
    bot_username: Optional[str],
    back_to_start: bool = False,
) -> InlineKeyboardMarkup:
    """
    Build the inline keyboard for /start and its sub-screens.

    Args:
        is_group: Whether the menu is rendered inside a group.
        bot_username: Needed for the "add me to a group" deep link.
        back_to_start: Render the sub-screen variant (Back + Close) rather than
            the landing variant.
    """
    if back_to_start:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(f"{_ICON_BACK} Back", callback_data="menu:start"),
            InlineKeyboardButton(f"{_ICON_CLOSE} Close", callback_data="menu:close"),
        ]])

    rows = [[
        InlineKeyboardButton(f"{_ICON_HELP} Commands", callback_data="menu:help"),
        InlineKeyboardButton(f"{_ICON_PING} Ping", callback_data="menu:ping"),
    ]]
    # Telegram only accepts ?startgroup deep links in private chats.
    if not is_group and bot_username:
        rows.append([
            InlineKeyboardButton(
                f"{_ICON_ADD} Add me to a group",
                url=f"https://t.me/{bot_username}?startgroup=true",
            )
        ])
    rows.append([
        InlineKeyboardButton(f"{_ICON_CLOSE} Close", callback_data="menu:close")
    ])
    return InlineKeyboardMarkup(rows)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start — onboarding pitch plus the inline menu.

    Deep links work too: ``t.me/<bot>?start=help`` jumps straight to the command
    reference, which is handy when linking from the README or the website.
    """
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    is_group = chat.type in _GROUP_TYPES
    bot_username = context.bot.username

    # Deep-link payload: ?start=help / ?start=commands skips the pitch.
    if context.args and context.args[0].lower() in ("help", "commands"):
        await message.reply_html(
            build_help_text(),
            reply_markup=build_menu(is_group, bot_username, back_to_start=True),
        )
        return

    await message.reply_html(
        build_start_text(is_group),
        reply_markup=build_menu(is_group, bot_username),
        disable_web_page_preview=True,
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route taps on the /start inline menu (callback data prefix ``menu:``)."""
    query = update.callback_query
    if query is None:
        return
    # Acknowledge first, even if rendering below fails — otherwise the client
    # shows a spinner on the tapped button.
    await query.answer()

    message = query.message
    if message is None:
        return

    action = (query.data or "").split(":", 1)[-1]
    is_group = is_group_chat(message)
    bot_username = context.bot.username

    if action == "close":
        try:
            await message.delete()
        except Exception as e:
            logger.debug(f"Menu close failed in chat {getattr(message.chat, 'id', '?')}: {e}")
        return

    if action == "help":
        text = build_help_text()
        markup = build_menu(is_group, bot_username, back_to_start=True)
    elif action == "ping":
        text = await build_ping_text(context)
        markup = build_menu(is_group, bot_username, back_to_start=True)
    else:
        # "start" (or any unexpected payload) returns to the landing screen.
        text = build_start_text(is_group)
        markup = build_menu(is_group, bot_username)

    await render_menu(query, context, text, markup)

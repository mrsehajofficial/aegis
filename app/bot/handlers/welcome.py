"""
welcome.py — Aegis group commands: rules, welcome/goodbye, settings.
"""
import html
import logging

from telegram import Update, Chat, User
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)

# ── Default message templates ──────────────────────────────────────────────────
# Placeholders are substituted with .replace() (never str.format), so admin
# custom messages may freely contain braces.
DEFAULT_WELCOME_MESSAGE = (
    "👋 Welcome to {group}, {name}!\n\n"
    "I'm <b>{bot}</b>, this group's management assistant. "
    "Read the rules with /rules and see everything I can do with /help."
)
DEFAULT_GOODBYE_MESSAGE = (
    "👋 {name} just left {group}. It was nice having you here — take care!"
)


def _display_name(user) -> str:
    """Best-effort human-readable name for a Telegram user/bot."""
    if user is None:
        return "friend"
    if isinstance(user, User):
        return user.full_name or user.username or str(user.id)
    return getattr(user, "full_name", None) or getattr(user, "username", None) or str(getattr(user, "id", "friend"))


def _render_template(template: str, **values) -> str:
    """Substitute {placeholders} safely without str.format brace semantics."""
    text = template if template is not None else ""
    for key, val in values.items():
        text = text.replace("{" + key + "}", str(val))
    return text


async def _require_group(update: Update):
    chat = update.effective_chat
    if chat is None or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        if update.effective_message:
            await update.effective_message.reply_text("This command only works in groups.")
        return None
    return chat


async def _get_settings(chat_id: int):
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat_id)
        if not g:
            return None, None
        s = await SettingsRepository(session).get_or_create(g.id)
        # detach values before session closes
        data = {"warn_limit": s.warn_limit, "welcome_enabled": s.welcome_enabled,
                "goodbye_enabled": s.goodbye_enabled, "anti_flood_enabled": s.anti_flood_enabled,
                "anti_spam_enabled": s.anti_spam_enabled, "log_enabled": s.log_enabled,
                "reports_enabled": s.reports_enabled, "rules": s.rules,
                "welcome_message": s.welcome_message, "goodbye_message": s.goodbye_message}
        return g, data


async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "welcome") is None:
        return
    chat = update.effective_chat
    g, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    state = "<b>On</b>" if s["welcome_enabled"] else "<b>Off</b>"
    template = s["welcome_message"] or DEFAULT_WELCOME_MESSAGE
    preview = _render_template(
        template.strip(),
        name="new member",
        group=html.escape(g.title or "this group"),
        bot=html.escape(settings.BOT_NAME),
    )
    if s["welcome_enabled"]:
        await update.effective_message.reply_html(
            f"<b>Welcome message</b> — {state}\n\n{preview}\n\n"
            f"<i>Customize: /setwelcome on|off|&lt;text&gt;|default</i>")
    else:
        await update.effective_message.reply_html(
            f"<b>Welcome message</b> — {state}\n\n{preview}\n\n"
            f"<i>Welcome messages are currently off. Enable them with /setwelcome on.</i>")


async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setwelcome") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("on", "enable", "yes"):
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, welcome_enabled=True)
            await session.commit()
        await update.effective_message.reply_text("Welcome messages enabled.")
    elif arg in ("off", "disable", "no"):
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, welcome_enabled=False)
            await session.commit()
        await update.effective_message.reply_text("Welcome messages disabled.")
    elif arg == "default":
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, welcome_message=None)
            await session.commit()
        await update.effective_message.reply_text("Welcome message restored to the default.")
    else:
        text = " ".join(context.args or []).strip()
        if not text:
            await update.effective_message.reply_text(
                "Usage: /setwelcome on|off|<text>|default\n"
                "Example: /setwelcome 👋 Hi {name}, welcome to {group}!")
            return
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, welcome_message=text)
            await session.commit()
        await update.effective_message.reply_text("Custom welcome message saved. See it with /welcome.")


async def goodbye_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "goodbye") is None:
        return
    chat = update.effective_chat
    g, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    state = "<b>On</b>" if s["goodbye_enabled"] else "<b>Off</b>"
    template = s["goodbye_message"] or DEFAULT_GOODBYE_MESSAGE
    preview = _render_template(
        template.strip(),
        name="member",
        group=html.escape(g.title or "this group"),
        bot=html.escape(settings.BOT_NAME),
    )
    if s["goodbye_enabled"]:
        await update.effective_message.reply_html(
            f"<b>Goodbye message</b> — {state}\n\n{preview}\n\n"
            f"<i>Customize: /setgoodbye on|off|&lt;text&gt;|default</i>")
    else:
        await update.effective_message.reply_html(
            f"<b>Goodbye message</b> — {state}\n\n{preview}\n\n"
            f"<i>Goodbye messages are currently off. Enable them with /setgoodbye on.</i>")


async def setgoodbye_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setgoodbye") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("on", "enable", "yes"):
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, goodbye_enabled=True)
            await session.commit()
        await update.effective_message.reply_text("Goodbye messages enabled.")
    elif arg in ("off", "disable", "no"):
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, goodbye_enabled=False)
            await session.commit()
        await update.effective_message.reply_text("Goodbye messages disabled.")
    elif arg == "default":
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, goodbye_message=None)
            await session.commit()
        await update.effective_message.reply_text("Goodbye message restored to the default.")
    else:
        text = " ".join(context.args or []).strip()
        if not text:
            await update.effective_message.reply_text(
                "Usage: /setgoodbye on|off|<text>|default\n"
                "Example: /setgoodbye 👋 {name} left {group}!")
            return
        async with get_session() as session:
            g = await GroupRepository(session).get_by_telegram_id(chat.id)
            if not g:
                await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
                return
            await SettingsRepository(session).update(g.id, goodbye_message=text)
            await session.commit()
        await update.effective_message.reply_text("Custom goodbye message saved. See it with /goodbye.")


async def _send_join_or_leave_message(
    bot, chat_id: int, kind: str, names=None
) -> bool:
    """Post the configured welcome/goodbye message to a chat if enabled.

    Returns True when a message was actually sent. Falls back to the built-in
    templates when the group has no custom text stored.
    """
    if kind not in ("welcome", "goodbye"):
        return False
    names = [name for name in (names or []) if name]

    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat_id)
        if g is None:
            return False
        s = await SettingsRepository(session).get_or_create(g.id)
        enabled = s.welcome_enabled if kind == "welcome" else s.goodbye_enabled
        template = s.welcome_message if kind == "welcome" else s.goodbye_message
        group_title = g.title or "this group"

    if not enabled:
        return False

    template = (template or (DEFAULT_WELCOME_MESSAGE if kind == "welcome" else DEFAULT_GOODBYE_MESSAGE)).strip()
    name_text = ", ".join(html.escape(n) for n in names) or "friend"
    text = _render_template(
        template,
        name=name_text,
        group=html.escape(group_title),
        bot=html.escape(settings.BOT_NAME),
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(
            f"Could not send {kind} message to chat {chat_id} "
            f"(bot may have been removed or lacks permission): {e}"
        )
        return False


async def handle_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post welcome/goodbye messages when any member (user or bot) joins or leaves.

    Uses ChatMemberHandler.CHAT_MEMBER updates, which fire for *every* member of
    the group except the bot itself (that one arrives as MY_CHAT_MEMBER and is
    handled in lifecycle.py).
    """
    cmu = update.chat_member
    if cmu is None:
        return
    chat = cmu.chat
    if chat is None or chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return

    old_status = (cmu.old_chat_member.status.value if cmu.old_chat_member else "")
    new_status = (cmu.new_chat_member.status.value if cmu.new_chat_member else "")
    # cmu.user may be None for anonymous admin actions or channel posts
    name = _display_name(cmu.user) if cmu.user else "a member"

    if old_status in ("left", "kicked") and new_status in ("member", "administrator", "restricted"):
        await _send_join_or_leave_message(context.bot, chat.id, "welcome", [name])
    elif new_status in ("left", "kicked") and old_status in (
        "member", "administrator", "restricted", "creator"
    ):
        await _send_join_or_leave_message(context.bot, chat.id, "goodbye", [name])


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "rules") is None:
        return
    chat = update.effective_chat
    _, s = await _get_settings(chat.id)
    if not s:
        await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
        return
    if not s["rules"]:
        await update.effective_message.reply_text("No rules have been set. Administrators can add them with /setrules <text>.")
        return
    await update.effective_message.reply_html(f"<b>Group Rules</b>\n\n{html.escape(s['rules'])}")


async def setrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setrules") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    text = " ".join(context.args or []).strip()
    if not text and update.effective_message.reply_to_message and update.effective_message.reply_to_message.text:
        text = update.effective_message.reply_to_message.text.strip()
    if not text:
        await update.effective_message.reply_text("Usage: /setrules <text> (or reply with /setrules)")
        return
    if text.lower() in ("clear", "off", "none", "delete"):
        text = None
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        await SettingsRepository(session).update(g.id, rules=text)
        await session.commit()
    await update.effective_message.reply_text("Rules cleared." if text is None else "Group rules updated.")


async def setwarnlimit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update, context, "setwarnlimit") is None:
        return
    chat = update.effective_chat
    if not await is_admin_or_above(update, context):
        await update.effective_message.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /setwarnlimit <number 1-20>")
        return
    n = max(1, min(20, int(context.args[0])))
    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await update.effective_message.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        await SettingsRepository(session).update(g.id, warn_limit=n)
        await session.commit()
    await update.effective_message.reply_html(f"Warn limit set to <b>{n}</b>.")

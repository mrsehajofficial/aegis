import logging
import os
import sys

from telegram import BotCommand, BotCommandScopeAllGroupChats
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ChatMemberHandler,
    MessageHandler,
    filters as ptb_filters,
)
from telegram.request import HTTPXRequest

from app.config.settings import settings
from app.bot.handlers.commands import (
    help_command,
    ping_command,
    id_command,
    info_command,
    admins_command,
)
from app.bot.handlers.dashboard import dashboard_command
from app.bot.handlers.start import start_command, menu_callback
from app.bot.handlers.moderation import (
    ban_command,
    unban_command,
    kick_command,
    mute_command,
    unmute_command,
    warn_command,
    warnings_command,
    resetwarns_command,
    purge_command,
    pin_command,
    unpin_command,
    logs_command,
)
from app.bot.handlers.filters import filter_command, filters_command, stop_command, check_filters
from app.bot.handlers.welcome import (
    welcome_command,
    setwelcome_command,
    goodbye_command,
    setgoodbye_command,
    rules_command,
    setrules_command,
    setwarnlimit_command,
    handle_chat_member,
)
from app.bot.handlers.settings_ui import settings_command, settings_callback
from app.bot.handlers.lifecycle import handle_my_chat_member
from app.bot.handlers.errors import error_handler
from app.bot.handlers.group_protection import (
    setantiflood_command,
    setantispam_command,
    lock_command,
    unlock_command,
    locktypes_command,
    addblacklist_command,
    blacklist_command,
    rmblacklist_command,
    check_protection,
)
from app.bot.handlers.tracking import track_members
from app.bot.handlers.reports import report_command, setreports_command
from app.bot.handlers.stats import stats_command, mark_started
from app.bot.handlers.captcha import (
    handle_captcha_join,
    verify_callback,
    setcaptcha_command,
)
from app.bot.handlers.notes import (
    save_note_command,
    get_note_command,
    notes_command,
    clear_note_command,
    check_notes_in_message,
)
from app.bot.handlers.import_rose import importfromrose_command

logger = logging.getLogger(__name__)

# Command menu published to Telegram on startup (the client's command list).
# Declared once and rendered for both private chats and groups — minus /start,
# which is noise inside a group.
_COMMANDS = [
    BotCommand("start", "Show the menu and get started"),
    BotCommand("help", "Full command reference"),
    BotCommand("ping", "Bot latency, database and uptime"),
    BotCommand("id", "Show chat, user and message IDs"),
    BotCommand("info", "Profile and role of a user"),
    BotCommand("admins", "List group administrators"),
    BotCommand("rules", "Show the group rules"),
    BotCommand("setrules", "Set the group rules"),
    BotCommand("settings", "Group settings control panel"),
    BotCommand("stats", "Group health: members, warnings, actions"),
    BotCommand("dashboard", "Open the Dashboard Mini App"),
    BotCommand("welcome", "Show the welcome message"),
    BotCommand("setwelcome", "Turn welcome on/off or set its text"),
    BotCommand("goodbye", "Show the goodbye message"),
    BotCommand("setgoodbye", "Turn goodbye on/off or set its text"),
    BotCommand("setwarnlimit", "Warnings before action (1-20)"),
    BotCommand("ban", "Ban a member"),
    BotCommand("unban", "Remove a ban"),
    BotCommand("kick", "Remove without banning"),
    BotCommand("mute", "Mute a member"),
    BotCommand("unmute", "Remove a mute"),
    BotCommand("warn", "Issue a warning"),
    BotCommand("warnings", "View a user's warnings"),
    BotCommand("resetwarns", "Clear a user's warnings"),
    BotCommand("purge", "Delete from the replied message onward"),
    BotCommand("pin", "Pin the replied message"),
    BotCommand("unpin", "Unpin the pinned message"),
    BotCommand("logs", "Recent moderation log"),
    BotCommand("report", "Report a message to admins"),
    BotCommand("reports", "Turn reports on/off"),
    BotCommand("setantiflood", "Toggle anti-flood"),
    BotCommand("setantispam", "Toggle anti-spam"),
    BotCommand("setcaptcha", "Configure the join captcha"),
    BotCommand("lock", "Lock a content type"),
    BotCommand("unlock", "Unlock a content type"),
    BotCommand("locktypes", "List lockable content types"),
    BotCommand("addblacklist", "Add a banned word"),
    BotCommand("blacklist", "List banned words"),
    BotCommand("rmblacklist", "Remove a banned word"),
    BotCommand("save", "Save a note"),
    BotCommand("get", "Retrieve a note"),
    BotCommand("notes", "List all notes"),
    BotCommand("clear", "Remove a note"),
    BotCommand("filter", "Add an auto-reply filter"),
    BotCommand("filters", "List active filters"),
    BotCommand("stop", "Remove an auto-reply filter"),
    BotCommand("importfromrose", "Migrate blacklist/filters/notes from a CSV"),
]

_GROUP_COMMANDS = [c for c in _COMMANDS if c.command != "start"]


async def _post_init(application: Application) -> None:
    """
    PTB post_init hook — publish the command list to Telegram on startup.

    Without this the commands never appear in the client's ☰ menu, so every user
    has to memorise the syntax; that is the biggest usability gap in classic
    group-management bots. Registration is best-effort: if Telegram is slow or
    unreachable the bot still runs, only the menu stays empty.
    """
    try:
        await application.bot.set_my_commands(_COMMANDS)
        await application.bot.set_my_commands(
            _GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats()
        )
        logger.info(f"Registered {len(_COMMANDS)} commands with Telegram.")
    except Exception as e:
        logger.warning(f"Could not register the command menu: {e}")
    # Reference point for the uptime figure in /ping and /stats.
    mark_started()


def _get_proxy_url() -> str | None:
    """Resolve the proxy URL, auto-detecting PythonAnywhere if applicable.

    PythonAnywhere free accounts require routing all outbound HTTP/HTTPS requests
    through http://proxy.server:3128; direct connections are blocked by their firewall.
    """
    if settings.HTTP_PROXY_URL and settings.HTTP_PROXY_URL.strip():
        return settings.HTTP_PROXY_URL.strip()

    # Detect PythonAnywhere environment where proxy is mandatory
    is_pa = bool(
        os.environ.get("PYTHONANYWHERE_DOMAIN")
        or os.environ.get("PYTHONANYWHERE_SITE")
        or "pythonanywhere" in sys.executable.lower()
        or "pythonanywhere" in os.environ.get("VIRTUAL_ENV", "").lower()
        or "pythonanywhere" in os.path.expanduser("~").lower()
        or os.path.exists("/var/www/aegistelebot_pythonanywhere_com_wsgi.py")
    )
    if is_pa:
        return (
            os.environ.get("https_proxy")
            or os.environ.get("http_proxy")
            or "http://proxy.server:3128"
        )

    # Standard environment proxy fallback
    env_proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    return env_proxy if env_proxy else None


def _make_request() -> HTTPXRequest:
    """Build the bot's HTTP request backend."""
    proxy = _get_proxy_url()
    httpx_kwargs = {}
    if not proxy:
        httpx_kwargs["trust_env"] = False

    return HTTPXRequest(
        connection_pool_size=settings.HTTP_POOL_SIZE if settings.HTTP_POOL_SIZE else 100,
        connect_timeout=settings.HTTP_CONNECT_TIMEOUT,
        read_timeout=settings.HTTP_READ_TIMEOUT,
        write_timeout=settings.HTTP_WRITE_TIMEOUT,
        pool_timeout=10.0,
        proxy=proxy,
        httpx_kwargs=httpx_kwargs if httpx_kwargs else None,
    )


def build_application() -> Application:
    """Build and configure the PTB Application with all registered handlers."""
    app = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .request(_make_request())
        .post_init(_post_init)
        .build()
    )

    # ── Onboarding ────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^cfg:"))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern=r"^captcha:"))

    # ── Information Commands ──────────────────────────────────────────────────
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("admins", admins_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("dashboard", dashboard_command))

    # ── Moderation Commands ─────────────────────────────────────────────────────
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("warnings", warnings_command))
    app.add_handler(CommandHandler("resetwarns", resetwarns_command))
    app.add_handler(CommandHandler("purge", purge_command))
    app.add_handler(CommandHandler("pin", pin_command))
    app.add_handler(CommandHandler("unpin", unpin_command))
    app.add_handler(CommandHandler("logs", logs_command))

    # ── Group / Welcome Commands ──────────────────────────────────────────────
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CommandHandler("setrules", setrules_command))
    app.add_handler(CommandHandler("welcome", welcome_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("goodbye", goodbye_command))
    app.add_handler(CommandHandler("setgoodbye", setgoodbye_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("setwarnlimit", setwarnlimit_command))

    # ── Group Protection Commands ─────────────────────────────────────────────
    app.add_handler(CommandHandler("setantiflood", setantiflood_command))
    app.add_handler(CommandHandler("setantispam", setantispam_command))
    app.add_handler(CommandHandler("setcaptcha", setcaptcha_command))
    app.add_handler(CommandHandler("lock", lock_command))
    app.add_handler(CommandHandler("unlock", unlock_command))
    app.add_handler(CommandHandler("locktypes", locktypes_command))
    app.add_handler(CommandHandler("addblacklist", addblacklist_command))
    app.add_handler(CommandHandler("blacklist", blacklist_command))
    app.add_handler(CommandHandler("rmblacklist", rmblacklist_command))

    # ── Reports Commands ─────────────────────────────────────────────────────
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("reports", setreports_command))

    # ── Notes Commands ───────────────────────────────────────────────────────
    app.add_handler(CommandHandler("save", save_note_command))
    app.add_handler(CommandHandler("get", get_note_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("clear", clear_note_command))

    # ── Filter Commands ───────────────────────────────────────────────────────
    app.add_handler(CommandHandler("filter", filter_command))
    app.add_handler(CommandHandler("filters", filters_command))
    app.add_handler(CommandHandler("stop", stop_command))

    # ── Migration from MissRose ───────────────────────────────────────────────
    # Two entry paths into one handler: the command sent as a document caption,
    # and the command replying to a document sent separately.
    app.add_handler(CommandHandler("importfromrose", importfromrose_command))
    app.add_handler(
        MessageHandler(
            ptb_filters.Document.ALL
            & ptb_filters.CaptionRegex(r"^/importfromrose\b"),
            importfromrose_command,
        )
    )

    # ── Message Handlers (non-command text) ──────────────────────────────────
    # Filter auto-replies (text only — filters are keyword triggers)
    app.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND, check_filters))
    # Notes (#keyword auto-detection)
    app.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND, check_notes_in_message, block=False), group=3)
    # Protection: flood/spam/blacklist — covers ALL user content messages,
    # not just text.  Stickers, photos, videos, voice notes can also be used
    # to flood, so we must not exclude them.
    app.add_handler(
        MessageHandler(
            ~ptb_filters.COMMAND & ~ptb_filters.StatusUpdate.ALL,
            check_protection,
            block=False,
        ),
        group=2,
    )

    # ── Member tracking (username cache for @user resolution) ─────────────────
    # Separate handler group + block=False: runs alongside commands without
    # slowing them down or swallowing updates.
    app.add_handler(
        MessageHandler(ptb_filters.ALL, track_members, block=False), group=1)

    # ── Member Join / Leave (welcome & goodbye messages) ──────────────────────
    # Fires for any user/bot whose membership status changes (except the bot
    # itself, which arrives as MY_CHAT_MEMBER and is handled in lifecycle.py).
    app.add_handler(
        ChatMemberHandler(handle_chat_member, ChatMemberHandler.CHAT_MEMBER, block=False),
        group=1,
    )

    # ── Join Captcha (mute + challenge new members) ───────────────────────────
    # Same CHAT_MEMBER stream as the welcome handler; independent so captcha
    # failures never suppress a welcome message (and vice versa).
    app.add_handler(
        ChatMemberHandler(handle_captcha_join, ChatMemberHandler.CHAT_MEMBER, block=False),
        group=1,
    )

    # ── Bot Lifecycle (my_chat_member) ────────────────────────────────────────
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # ── Global Error Handler ──────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    logger.info("All handlers registered.")
    return app

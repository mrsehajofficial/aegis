import logging
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ChatMemberHandler,
    MessageHandler,
    filters as ptb_filters,
)

from app.config.settings import settings
from app.bot.handlers.commands import (
    help_command,
    id_command,
    info_command,
    admins_command,
)
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
    settings_command,
    setwarnlimit_command,
    handle_chat_member,
)
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
from app.bot.handlers.notes import (
    save_note_command,
    get_note_command,
    notes_command,
    clear_note_command,
    check_notes_in_message,
)

logger = logging.getLogger(__name__)


def build_application() -> Application:
    """Build and configure the PTB Application with all registered handlers."""
    app = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .build()
    )

    # ── Information Commands ──────────────────────────────────────────────────
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("admins", admins_command))

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

    # ── Message Handlers (non-command text) ──────────────────────────────────
    # Filter auto-replies
    app.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND, check_filters))
    # Notes (#keyword auto-detection)
    app.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND, check_notes_in_message, block=False), group=3)
    # Protection: flood/spam/blacklist (group 2, block=False)
    app.add_handler(
        MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND, check_protection, block=False), group=2
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

    # ── Bot Lifecycle (my_chat_member) ────────────────────────────────────────
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # ── Global Error Handler ──────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    logger.info("All handlers registered.")
    return app

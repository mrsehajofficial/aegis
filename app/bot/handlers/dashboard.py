"""
dashboard.py - /dashboard command to open the Mini App
"""
import logging
from telegram import Chat, Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from app.bot.helpers.ensure_group import ensure_group_registered
from app.bot.middleware.auth import is_admin_or_above
from app.config.settings import settings

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://your-domain.com/miniapp"


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the Aegis Dashboard Mini App.

    Works in both private chats (the Mini App lets you pick a group) and in
    groups (only admins can open it for that group).  The button uses the
    `web_app` field so Telegram opens it as a proper Mini App with the
    Web Apps JS bridge rather than a plain browser link.
    """
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    if chat is None or message is None or user is None:
        return

    # In groups the caller must be an admin (and the group must be registered).
    # In private chats anyone can open the Mini App — the API authorizes the
    # caller via the signed initData payload, not via this command.
    if chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        db_id = await ensure_group_registered(chat, context.bot)
        if db_id is None:
            await message.reply_text(
                "Group registration failed. Please try again shortly."
            )
            return
        if not await is_admin_or_above(update, context):
            await message.reply_html(
                "<b>Access denied.</b>\nOnly group administrators can open the "
                "dashboard from a group. Open a private chat with me and use /dashboard instead."
            )
            return

    url = settings.MINIAPP_URL.strip() if settings.MINIAPP_URL else DASHBOARD_URL
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    if not url.endswith("/miniapp") and "/miniapp" not in url:
        url = f"{url.rstrip('/')}/miniapp"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🛡️ Open Dashboard", web_app=WebAppInfo(url=url))]
    ])

    await message.reply_text(
        f"<b>🛡️ Aegis Dashboard</b>\n\n"
        f"Manage your group visually:\n"
        f"• Toggle features (welcome, goodbye, anti-flood, anti-spam)\n"
        f"• Configure warning limits\n"
        f"• Set welcome & goodbye messages\n"
        f"• Manage group rules\n"
        f"• Add/edit/delete filters\n"
        f"• Manage blacklist with actions\n"
        f"• Save and retrieve notes\n\n"
        f"Tap to open the dashboard.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    logger.info(f"Dashboard opened by @{user.username or user.id} in chat {chat.id}")

"""
dashboard.py - /dashboard command to open the Mini App
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)

from app.config.settings import settings

DASHBOARD_URL = "https://your-domain.com/miniapp"


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the Aegis Dashboard Mini App."""
    if await guard(update, context, "dashboard") is None:
        return
    
    chat = update.effective_chat
    user = update.effective_user
    
    if not await is_admin_or_above(update):
        await update.effective_message.reply_html("<b>Access denied.</b>")
        return
    
    if chat is None:
        await update.effective_message.reply_text("This command only works in groups.")
        return
    
    url = settings.MINIAPP_URL.strip() if settings.MINIAPP_URL else DASHBOARD_URL
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    if not url.endswith("/miniapp") and not "/miniapp" in url:
        url = f"{url.rstrip('/')}/miniapp"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🛡️ Open Dashboard", url=url)]
    ])
    
    await update.effective_message.reply_text(
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
        parse_mode="HTML"
    )
    logger.info(f"Dashboard opened by @{user.username or user.id} in chat {chat.id}")

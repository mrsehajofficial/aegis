"""
business.py — Telegram Business integration and chat automation handlers.

Handles:
- business_connection updates (linking/unlinking Telegram Business accounts)
- business_message updates (incoming customer messages in private chats)
- Messaging on behalf of the user using business_connection_id
- Configuration commands and inline control panel (/business, /biz, /bizrules, /bizadd, etc.)
"""
import html
import logging
from typing import Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.services.business import (
    register_business_connection,
    get_business_connection_for_user,
    get_business_connection_by_id,
    toggle_auto_reply,
    toggle_greeting,
    toggle_away,
    set_greeting_message,
    set_away_message,
    add_business_rule,
    delete_business_rule,
    get_business_rules,
    evaluate_business_message,
)

logger = logging.getLogger(__name__)


# ── Telegram Business Connection Handler ──────────────────────────────────────


async def handle_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fired when a user connects or disconnects the bot via Telegram Settings > Telegram Business > Chatbots.
    """
    bc = update.business_connection
    if bc is None:
        return

    connection_id = bc.id
    user = bc.user
    user_id = user.id
    user_chat_id = bc.user_chat_id
    is_enabled = bc.is_enabled

    # Rights inspection (supports Bot API 8.0+ BusinessBotRights and fallback)
    rights = getattr(bc, "rights", None)
    if rights is not None:
        can_reply = getattr(rights, "can_reply", True)
    else:
        can_reply = getattr(bc, "can_reply", True)
    if can_reply is None:
        can_reply = True

    logger.info(
        "Telegram Business connection update: id=%s user=%d (@%s) enabled=%s can_reply=%s",
        connection_id,
        user_id,
        user.username or "none",
        is_enabled,
        can_reply,
    )

    await register_business_connection(
        connection_id=connection_id,
        user_id=user_id,
        user_chat_id=user_chat_id,
        can_reply=can_reply,
        is_enabled=is_enabled,
    )

    # Notify the user in their private chat with the bot
    target_chat_id = user_chat_id or user_id
    try:
        if is_enabled:
            reply_perm_text = "✅ Granted" if can_reply else "⚠️ Not granted (enable in Settings > Telegram Business > Chatbots)"
            text = (
                f"<b>💼 Telegram Business Connected!</b>\n\n"
                f"Your Telegram account is now connected with <b>{html.escape(settings.BOT_NAME)}</b>.\n"
                f"I can automatically respond to customer messages in your private chats on your behalf.\n\n"
                f"• <b>Status:</b> 🟢 Active\n"
                f"• <b>Reply Permission:</b> {reply_perm_text}\n"
                f"• <b>Starter Rules:</b> 4 default keywords (price, hours, support, hello) have been enabled.\n\n"
                f"Type /biz or /business to open your control panel and customize your responses!"
            )
            await context.bot.send_message(chat_id=target_chat_id, text=text, parse_mode="HTML")
        else:
            text = (
                f"<b>⚠️ Telegram Business Disconnected</b>\n\n"
                f"Your account was disconnected from <b>{html.escape(settings.BOT_NAME)}</b>.\n"
                f"Automated replies on your behalf have been paused."
            )
            await context.bot.send_message(chat_id=target_chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.debug("Could not send business status message to chat %d: %s", target_chat_id, e)


# ── Telegram Business Message Auto-Responder ──────────────────────────────────


async def handle_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fired when a message is received in a private chat connected via Telegram Business.
    Evaluates rules and sends automated replies on behalf of the business account.
    """
    biz_msg = update.business_message
    if biz_msg is None or not biz_msg.business_connection_id:
        return

    text = biz_msg.text or biz_msg.caption or ""
    if not text.strip():
        return

    from_user = biz_msg.from_user
    from_user_id = from_user.id if from_user else 0
    chat_id = biz_msg.chat_id
    connection_id = biz_msg.business_connection_id

    logger.debug(
        "Incoming business message in chat %d via connection %s from user %d: %r",
        chat_id,
        connection_id,
        from_user_id,
        text[:50],
    )

    try:
        reply = await evaluate_business_message(
            connection_id=connection_id,
            chat_id=chat_id,
            from_user_id=from_user_id,
            text=text,
        )
        if reply:
            await context.bot.send_message(
                chat_id=chat_id,
                text=reply,
                business_connection_id=connection_id,
            )
            logger.info("Sent business auto-reply to chat %d on behalf of user", chat_id)
    except Exception as e:
        logger.error("Failed to evaluate or send business auto-reply in chat %d: %s", chat_id, e, exc_info=True)


# ── Business Owner Dashboard & Settings UI ────────────────────────────────────


def build_business_markup(
    auto_reply_enabled: bool,
    greeting_enabled: bool,
    away_enabled: bool,
) -> InlineKeyboardMarkup:
    """Build the interactive inline keyboard for /business dashboard."""
    ar_icon = "🟢" if auto_reply_enabled else "🔴"
    gr_icon = "🟢" if greeting_enabled else "🔴"
    aw_icon = "🟢" if away_enabled else "🔴"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{ar_icon} Auto-Reply: {'ON' if auto_reply_enabled else 'OFF'}",
                callback_data="biz:toggle_autoreply",
            )
        ],
        [
            InlineKeyboardButton(
                f"{gr_icon} Greeting: {'ON' if greeting_enabled else 'OFF'}",
                callback_data="biz:toggle_greeting",
            ),
            InlineKeyboardButton(
                f"{aw_icon} Away Mode: {'ON' if away_enabled else 'OFF'}",
                callback_data="biz:toggle_away",
            ),
        ],
        [
            InlineKeyboardButton("📋 View Keywords", callback_data="biz:rules"),
            InlineKeyboardButton("ℹ️ Help / Setup", callback_data="biz:help"),
        ],
        [
            InlineKeyboardButton("✖️ Close", callback_data="biz:close")
        ],
    ])


async def _render_dashboard_text(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    conn = await get_business_connection_for_user(user_id)
    rules = await get_business_rules(user_id)

    if conn is None:
        text = (
            f"<b>💼 {html.escape(settings.BOT_NAME)} — Telegram Business Automation</b>\n\n"
            f"<b>Status:</b> 🔴 Not Connected\n\n"
            f"To connect this bot to your Telegram Business account:\n"
            f"1. Open <b>Telegram Settings</b> on your mobile app.\n"
            f"2. Go to <b>Telegram Business > Chatbots</b>.\n"
            f"3. Add <b>@{html.escape(settings.BOT_NAME.lower())}</b> as your chatbot.\n"
            f"4. Ensure <i>'Reply to messages'</i> permission is granted.\n\n"
            f"Once connected, you can manage automated responses on your behalf here!"
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Refresh Status", callback_data="biz:refresh"),
            InlineKeyboardButton("✖️ Close", callback_data="biz:close"),
        ]])
        return text, markup

    status_str = "🟢 Active" if conn.is_enabled else "🔴 Inactive"
    can_reply_str = "✅ Yes" if conn.can_reply else "❌ No (Check permissions in Settings)"
    auto_reply_str = "🟢 Enabled" if conn.auto_reply_enabled else "🔴 Disabled"
    greeting_str = "🟢 Enabled" if conn.greeting_enabled else "🔴 Disabled"
    away_str = "🟢 Enabled" if conn.away_enabled else "🔴 Disabled"

    text = (
        f"<b>💼 {html.escape(settings.BOT_NAME)} — Business Automation Panel</b>\n\n"
        f"• <b>Connection:</b> {status_str}\n"
        f"• <b>Can Reply On Behalf:</b> {can_reply_str}\n"
        f"• <b>Auto-Responder:</b> {auto_reply_str}\n"
        f"• <b>Greeting Message:</b> {greeting_str}\n"
        f"• <b>Away / Out-of-Office:</b> {away_str}\n"
        f"• <b>Active Keywords:</b> {len(rules)} rules\n\n"
        f"<i>Tap the buttons below to toggle features, or use /bizrules to view keywords.</i>"
    )
    markup = build_business_markup(
        auto_reply_enabled=conn.auto_reply_enabled,
        greeting_enabled=conn.greeting_enabled,
        away_enabled=conn.away_enabled,
    )
    return text, markup


async def business_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /business and /biz command."""
    user = update.effective_user
    if user is None:
        return

    chat = update.effective_chat
    if chat and chat.type != "private":
        bot_username = context.bot.username
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("Open in Private Chat", url=f"https://t.me/{bot_username}?start=biz")
        ]])
        await update.effective_message.reply_text(
            "Telegram Business management is only available in private chat.",
            reply_markup=markup,
        )
        return

    text, markup = await _render_dashboard_text(user.id)
    await update.effective_message.reply_html(text, reply_markup=markup)


async def biz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button clicks for the /business dashboard."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    user = update.effective_user
    if user is None:
        return

    data = query.data or ""
    action = data.split(":", 1)[-1]

    if action == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "toggle_autoreply":
        await toggle_auto_reply(user.id)
    elif action == "toggle_greeting":
        await toggle_greeting(user.id)
    elif action == "toggle_away":
        await toggle_away(user.id)
    elif action == "rules":
        rules = await get_business_rules(user.id)
        if not rules:
            r_text = (
                "<b>📋 Business Keyword Rules</b>\n\n"
                "No rules configured yet.\n"
                "Add one with: <code>/bizadd &lt;keyword&gt; &lt;response&gt;</code>"
            )
        else:
            lines = ["<b>📋 Active Business Keywords:</b>\n"]
            for r in rules:
                status = "🟢" if r.enabled else "⚪"
                lines.append(f"{status} <b>{html.escape(r.trigger)}</b> ({r.match_type}):\n<i>{html.escape(r.response)}</i>\n")
            r_text = "\n".join(lines)

        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Back to Dashboard", callback_data="biz:refresh"),
            InlineKeyboardButton("✖️ Close", callback_data="biz:close"),
        ]])
        await query.edit_message_text(r_text, parse_mode="HTML", reply_markup=markup)
        return
    elif action == "help":
        help_text = (
            "<b>📖 Business Chat Automation Guide</b>\n\n"
            "<b>Commands:</b>\n"
            "• <code>/biz</code> — Open dashboard & toggles\n"
            "• <code>/bizrules</code> — List all active keywords\n"
            "• <code>/bizadd &lt;keyword&gt; &lt;response&gt;</code> — Add or update a keyword\n"
            "• <code>/bizdel &lt;keyword&gt;</code> — Remove a keyword\n"
            "• <code>/bizgreeting &lt;text&gt;</code> — Set greeting message\n"
            "• <code>/bizaway &lt;text&gt;</code> — Set out-of-office message\n"
            "• <code>/bizstatus</code> — Connection diagnostics\n\n"
            "<b>How it works:</b>\n"
            "When someone sends a message to your personal chat containing a keyword, "
            "Aegis immediately sends the response on your behalf."
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Back to Dashboard", callback_data="biz:refresh"),
            InlineKeyboardButton("✖️ Close", callback_data="biz:close"),
        ]])
        await query.edit_message_text(help_text, parse_mode="HTML", reply_markup=markup)
        return

    # Default / refresh: render updated dashboard
    text, markup = await _render_dashboard_text(user.id)
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.debug("Failed to edit dashboard message: %s", e)


# ── Business Commands (Direct Text Commands) ──────────────────────────────────


async def bizrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /bizrules and /bizkeywords."""
    user = update.effective_user
    if user is None:
        return

    rules = await get_business_rules(user.id)
    if not rules:
        await update.effective_message.reply_html(
            "<b>No business rules found.</b>\n\n"
            "Add your first keyword with: <code>/bizadd &lt;keyword&gt; &lt;response&gt;</code>"
        )
        return

    lines = ["<b>📋 Active Business Auto-Replies:</b>\n"]
    for r in rules:
        status = "🟢" if r.enabled else "⚪"
        lines.append(f"{status} <b>{html.escape(r.trigger)}</b>:\n{html.escape(r.response)}\n")

    lines.append("<i>To delete a rule: /bizdel &lt;keyword&gt;</i>")
    await update.effective_message.reply_html("\n".join(lines))


async def bizadd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add or update a keyword rule: /bizadd <keyword> <response text...>"""
    user = update.effective_user
    if user is None:
        return

    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_html(
            "<b>Usage:</b> <code>/bizadd &lt;keyword&gt; &lt;response text&gt;</code>\n\n"
            "Example: <code>/bizadd pricing Our plans start at $99/mo.</code>"
        )
        return

    keyword = context.args[0].strip().lower()
    response = " ".join(context.args[1:]).strip()

    if len(keyword) > 100 or len(response) > 2000:
        await update.effective_message.reply_text(
            "Keyword or response too long (keyword max 100 chars, response max 2000 chars)."
        )
        return

    await add_business_rule(user_id=user.id, trigger=keyword, response=response)
    await update.effective_message.reply_html(
        f"✅ Business rule for keyword <code>{html.escape(keyword)}</code> saved!\n"
        f"When someone sends a message with this keyword, I will reply on your behalf."
    )


async def bizdel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a keyword rule: /bizdel <keyword>"""
    user = update.effective_user
    if user is None:
        return

    if not context.args:
        await update.effective_message.reply_html(
            "<b>Usage:</b> <code>/bizdel &lt;keyword&gt;</code>"
        )
        return

    keyword = context.args[0].strip().lower()
    deleted = await delete_business_rule(user_id=user.id, trigger=keyword)
    if deleted:
        await update.effective_message.reply_html(
            f"✅ Business rule for <code>{html.escape(keyword)}</code> removed."
        )
    else:
        await update.effective_message.reply_html(
            f"Rule for <code>{html.escape(keyword)}</code> not found."
        )


async def bizgreeting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set greeting message: /bizgreeting <text> or /bizgreeting off"""
    user = update.effective_user
    if user is None:
        return

    if not context.args:
        conn = await get_business_connection_for_user(user.id)
        current = conn.greeting_message if conn else None
        status = "🟢 ON" if conn and conn.greeting_enabled else "🔴 OFF"
        msg = html.escape(current) if current else "<i>Not set</i>"
        await update.effective_message.reply_html(
            f"<b>Greeting Message Status:</b> {status}\n\n"
            f"Current message:\n{msg}\n\n"
            f"• To update: <code>/bizgreeting &lt;your greeting text&gt;</code>\n"
            f"• To disable: <code>/bizgreeting off</code>"
        )
        return

    arg = " ".join(context.args).strip()
    if arg.lower() in ("off", "disable", "stop"):
        await toggle_greeting(user.id)
        await update.effective_message.reply_html("🔴 Business greeting disabled.")
    else:
        await set_greeting_message(user.id, arg)
        await update.effective_message.reply_html(
            f"✅ Business greeting set and enabled:\n\n{html.escape(arg)}"
        )


async def bizaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set away message: /bizaway <text> or /bizaway off"""
    user = update.effective_user
    if user is None:
        return

    if not context.args:
        conn = await get_business_connection_for_user(user.id)
        current = conn.away_message if conn else None
        status = "🟢 ON" if conn and conn.away_enabled else "🔴 OFF"
        msg = html.escape(current) if current else "<i>Not set</i>"
        await update.effective_message.reply_html(
            f"<b>Away / Out-of-Office Status:</b> {status}\n\n"
            f"Current message:\n{msg}\n\n"
            f"• To update: <code>/bizaway &lt;your away text&gt;</code>\n"
            f"• To disable: <code>/bizaway off</code>"
        )
        return

    arg = " ".join(context.args).strip()
    if arg.lower() in ("off", "disable", "stop"):
        await toggle_away(user.id)
        await update.effective_message.reply_html("🔴 Business away message disabled.")
    else:
        await set_away_message(user.id, arg)
        await update.effective_message.reply_html(
            f"✅ Business away message set and enabled:\n\n{html.escape(arg)}"
        )


async def bizstatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Diagnostics command /bizstatus."""
    user = update.effective_user
    if user is None:
        return

    conn = await get_business_connection_for_user(user.id)
    if not conn:
        await update.effective_message.reply_html(
            "<b>No Telegram Business connection found.</b>\n"
            "Connect the bot via Telegram Settings > Telegram Business > Chatbots."
        )
        return

    text = (
        f"<b>💼 Telegram Business Diagnostic Status</b>\n\n"
        f"• <b>Connection ID:</b> <code>{html.escape(conn.connection_id)}</code>\n"
        f"• <b>User ID:</b> <code>{conn.user_id}</code>\n"
        f"• <b>Is Enabled:</b> {'🟢 Yes' if conn.is_enabled else '🔴 No'}\n"
        f"• <b>Can Reply:</b> {'🟢 Yes' if conn.can_reply else '🔴 No'}\n"
        f"• <b>Auto-Reply:</b> {'🟢 ON' if conn.auto_reply_enabled else '🔴 OFF'}\n"
        f"• <b>Greeting Enabled:</b> {'🟢 ON' if conn.greeting_enabled else '🔴 OFF'}\n"
        f"• <b>Away Enabled:</b> {'🟢 ON' if conn.away_enabled else '🔴 OFF'}\n"
        f"• <b>Connected At:</b> {conn.connected_at.strftime('%Y-%m-%d %H:%M:%S UTC') if conn.connected_at else 'Unknown'}\n"
        f"• <b>Last Updated:</b> {conn.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC') if conn.updated_at else 'Unknown'}"
    )
    await update.effective_message.reply_html(text)

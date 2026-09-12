import html
import logging
import traceback
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global error handler. Logs exceptions and sends a clean error message to users.
    """
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Build a human-readable traceback for logging
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Log full traceback at DEBUG level for diagnostics
    logger.debug(f"Full traceback:\n{tb_string}")

    # If we have a message context, try to notify the user.
    # Send a fresh message instead of a reply — the original message may
    # already be gone (e.g. deleted by /purge), which would fail with
    # "Message to be replied not found".
    if isinstance(update, Update) and update.effective_chat and update.effective_message:
        error_type = type(context.error).__name__
        safe_error = html.escape(str(context.error))
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(f"<b>An error occurred while processing that command.</b>\n\n"
                      f"<code>{error_type}: {safe_error}</code>\n\n"
                      f"<i>The incident has been logged. If it persists, contact the bot administrator.</i>"),
                parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not send error message to user: {e}")

"""
menus.py — Shared redraw logic for inline-keyboard panels.

/start and /settings both swap the content of an existing message, and both hit
the same two awkward cases:

* Telegram rejects a no-op edit ("Message is not modified"), which happens
  whenever someone taps the same button twice.
* The original message may be gone, too old, or inaccessible.

Keeping this in one place means every panel behaves identically instead of each
re-implementing — and subtly diverging on — the fallbacks.
"""
import logging

logger = logging.getLogger(__name__)


async def render_menu(query, context, text: str, markup) -> None:
    """
    Replace a panel message in place, falling back to a fresh message.

    The fallback matters: without it a button silently does nothing when the
    original message cannot be edited. A "not modified" error is swallowed
    instead, because the screen is already showing the right thing.
    """
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        return
    except Exception as e:
        if "not modified" in str(e).lower():
            return  # The same screen was tapped twice — nothing to redraw.
        logger.debug(f"Panel edit failed, sending a new message instead: {e}")

    chat = getattr(getattr(query, "message", None), "chat", None)
    if chat is None:
        return
    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception as e:
        logger.warning(f"Panel render failed in chat {chat.id}: {e}")
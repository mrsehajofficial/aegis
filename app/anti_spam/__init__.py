"""
Anti-spam domain - combined checker for flood and spam.

Usage in a message handler:
    from app.anti_spam import AntiSpamChecker
    checker = AntiSpamChecker(context, chat_id, group_settings)
    action = await checker.check_message(message)
    # action is None if clean, or a string describing the action taken
"""
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from telegram import Message
from telegram.ext import ContextTypes

from app.anti_spam.flood import check_flood, reset_user
from app.anti_spam.reputation import (
    FLAG_THRESHOLD,
    contribute_to_feed,
    known_spam_groups,
    record_spam,
    salted_fingerprint,
    pseudonymize_chat_id,
)
from app.anti_spam.detector import (
    check_edited_spam,
    check_spam,
    check_text_abuse,
    count_mentions,
    count_urls,
)
from app.anti_spam.actions import delete_message_safely, mute_user, ban_user

logger = logging.getLogger(__name__)


@dataclass
class GroupProtectionSettings:
    anti_flood_enabled: bool = False
    anti_spam_enabled: bool = False
    flood_msg_limit: int = 5
    flood_window_seconds: float = 3.0
    flood_mute_minutes: int = 5
    spam_action: str = "delete"  # delete | warn | mute | ban


class AntiSpamChecker:
    """Combined flood + spam checker for group messages."""

    def __init__(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        settings: GroupProtectionSettings,
    ):
        self.context = context
        self.chat_id = chat_id
        self.settings = settings

    async def check_message(self, message: Message, is_edit: bool = False) -> Optional[str]:
        """
        Run flood and spam checks on a message.
        Returns a string describing the action taken, or None if message is clean.

        Args:
            message: The message to inspect
            is_edit: True when this is an ``edited_message`` update. Edits use a
                stricter rule (see :func:`check_edited_spam`) because spammers
                routinely post clean text and edit a link in afterwards.
        """
        if not message or not message.from_user:
            return None

        user_id = message.from_user.id
        text = message.text or message.caption or ""

        # -- Flood check ----------------------------------------------
        if self.settings.anti_flood_enabled:
            if await check_flood(
                self.chat_id, user_id,
                self.settings.flood_msg_limit,
                self.settings.flood_window_seconds,
            ):
                await reset_user(self.chat_id, user_id)
                muted = await mute_user(
                    self.context, self.chat_id, user_id,
                    timedelta(minutes=self.settings.flood_mute_minutes),
                )
                await delete_message_safely(message)
                if muted:
                    logger.info(f"Flood: muted user {user_id} in chat {self.chat_id}")
                    return "flood_mute"
                return "flood_detected"

        # -- Spam check -----------------------------------------------
        if self.settings.anti_spam_enabled and text:
            url_count = count_urls(text)
            mention_count = count_mentions(text)
            has_forward = message.forward_date is not None

            if is_edit:
                result = check_edited_spam(text, has_forward, url_count, mention_count)
            else:
                result = check_spam(text, has_forward, url_count, mention_count)

            # Structural abuse (zalgo, character floods, symbol walls) is
            # independent of keywords and links, so it layers on top of whichever
            # rule set ran above.
            for reason in check_text_abuse(text).reasons:
                result.add(reason)

            # Cross-group reputation: the fingerprint network. When the same
            # message (by normalised fingerprint) was flagged as spam in enough
            # *other* groups recently, it is spam here too — no local heuristic
            # can be bypassed by keeping a message just under every threshold.
            try:
                known = await known_spam_groups(text, self.chat_id)
            except Exception as e:  # never let the network block a message
                logger.debug(f"Reputation check failed in chat {self.chat_id}: {e}")
                known = 0
            if known >= FLAG_THRESHOLD:
                result.add(f"known spam pattern (flagged in {known} other groups)")

            if result.is_spam:
                action_taken = await self._handle_spam(message, result.reasons)
                # Confirmed verdicts grow the network, so other groups are
                # pre-warned against this exact message.
                try:
                    await record_spam(self.chat_id, text)
                except Exception as e:
                    logger.debug(f"Reputation record failed in chat {self.chat_id}: {e}")
                return action_taken

        return None

    async def _handle_spam(self, message: Message, reasons: list) -> str:
        """Handle a spam message based on configured action."""
        action = self.settings.spam_action
        user_id = message.from_user.id

        if action == "delete":
            await delete_message_safely(message)
            return "spam_deleted"
        elif action == "mute":
            await delete_message_safely(message)
            muted = await mute_user(self.context, self.chat_id, user_id)
            if muted:
                return "spam_muted"
            return "spam_detected"
        elif action == "ban":
            await delete_message_safely(message)
            banned = await ban_user(self.context, self.chat_id, user_id)
            if banned:
                return "spam_banned"
            return "spam_detected"
        else:
            await delete_message_safely(message)
            return "spam_deleted"

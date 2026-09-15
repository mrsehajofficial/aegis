"""
detector.py - Anti-spam detector.

Checks messages for spam patterns:
- URL flood (multiple links)
- Mention flood (multiple @mentions)
- Caps lock abuse (mostly uppercase text)
- Forwarded message flood
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List

from app.anti_spam.normalize import (
    combining_ratio,
    longest_repeat_run,
    non_alphanumeric_ratio,
)

logger = logging.getLogger(__name__)

# A link is matched as one unit so count_urls() cannot double-count it: matching
# only the "https://" prefix and then the domain again would report one URL twice.
URL_PATTERN = re.compile(r"(?:https?://|www\.|t\.me/)\S+", re.IGNORECASE)

# Schemes are optional in practice — "bit.ly/x" and "spam.ru" are links too. The
# TLD list is limited to endings spammers actually register, so ordinary dotted
# words such as "file.txt" or "e.g." are not mistaken for links.
BARE_DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9][a-z0-9-]*\.)+"
    r"(?:com|net|org|info|biz|online|site|shop|store|link|click|live|"
    r"xyz|top|club|app|dev|io|co|me|ly|ru|su|by|ua|kz|pw|cc|tk|ml|ga|cf|gq)"
    r"\b(?:/\S*)?",
    re.IGNORECASE,
)

MENTION_PATTERN = re.compile(r"@\w{5,}")

# Common spam indicators
SPAM_DOMAINS = {"t.me", "telegram.me", "bit.ly", "tinyurl.com"}


@dataclass
class SpamCheckResult:
    is_spam: bool = False
    reasons: List[str] = field(default_factory=list)

    def add(self, reason: str) -> None:
        self.is_spam = True
        self.reasons.append(reason)


def check_spam(
    text: str,
    has_forward: bool = False,
    url_count: int = 0,
    mention_count: int = 0,
) -> SpamCheckResult:
    """
    Check a message for spam patterns.

    Args:
        text: The message text to check
        has_forward: Whether the message is a forwarded message
        url_count: Number of URLs detected in the message
        mention_count: Number of @mentions detected in the message

    Returns:
        SpamCheckResult with is_spam flag and list of reasons
    """
    result = SpamCheckResult()

    if not text:
        return result

    # Caps lock check (text must be long enough to be meaningful)
    if len(text) >= 10:
        upper_count = sum(1 for c in text if c.isupper())
        alpha_count = sum(1 for c in text if c.isalpha())
        if alpha_count >= 10 and (upper_count / alpha_count) >= 0.7:
            result.add("excessive caps")

    # URL flood (3+ URLs)
    if url_count >= 3:
        result.add(f"url flood ({url_count} links)")

    # Mention flood (5+ mentions)
    if mention_count >= 5:
        result.add(f"mention flood ({mention_count} mentions)")

    # Forward flood indicator
    if has_forward and len(text) >= 20:
        result.add("frequent forwarding")

    return result


def check_edited_spam(
    text: str,
    has_forward: bool = False,
    url_count: int = 0,
    mention_count: int = 0,
) -> SpamCheckResult:
    """
    Stricter variant of :func:`check_spam` for *edited* messages.

    A well-known bypass: post a harmless message, wait for filters to pass it,
    then edit it to add a link. Telegram never sends the previous text, so we
    cannot diff — instead we treat an edit that contains *any* link, or a burst
    of mentions, as spam without waiting for the normal flood thresholds.

    Args:
        text: The edited message text
        has_forward: Whether the message is a forwarded message
        url_count: Number of links detected in the message
        mention_count: Number of @mentions detected in the message

    Returns:
        SpamCheckResult with is_spam flag and list of reasons
    """
    result = check_spam(
        text,
        has_forward=has_forward,
        url_count=url_count,
        mention_count=mention_count,
    )
    if url_count >= 1:
        result.add(f"link in edited message ({url_count})")
    elif mention_count >= 3:
        result.add(f"mention burst in edited message ({mention_count})")
    return result


def count_urls(text: str) -> int:
    """Count links in text (scheme-qualified, www-prefixed, t.me or bare domain)."""
    if not text:
        return 0
    # Blank out full links first: their domain part would otherwise match the
    # bare-domain pattern a second time ("https://spam.ru" is one link, not two).
    remainder = URL_PATTERN.sub(" ", text)
    return len(URL_PATTERN.findall(text)) + len(BARE_DOMAIN_PATTERN.findall(remainder))


def count_mentions(text: str) -> int:
    """Count @mentions in text."""
    if not text:
        return 0
    return len(MENTION_PATTERN.findall(text))


def check_text_abuse(
    text: str,
    zalgo_threshold: float = 0.25,
    noise_threshold: float = 0.6,
    repeat_threshold: int = 8,
) -> SpamCheckResult:
    """
    Structural abuse signals that survive link and keyword filters.

    Catches messages with no banned words and no links that are still hostile:
    zalgo text, character floods and walls of symbols. Thresholds are
    deliberately loose so ordinary enthusiasm ("sooooo good", "!!!!") passes.
    """
    result = SpamCheckResult()
    if not text:
        return result

    ratio = combining_ratio(text)
    if ratio >= zalgo_threshold:
        result.add(f"zalgo text ({ratio:.0%} combining marks)")

    run = longest_repeat_run(text)
    if run >= repeat_threshold:
        result.add(f"character flood (run of {run})")

    # Short messages are naturally punctuation-heavy ("hi!!!"), so only judge
    # symbol density once there is enough text for it to be meaningful.
    if len(text) >= 20:
        noise = non_alphanumeric_ratio(text)
        if noise >= noise_threshold:
            result.add(f"symbol flood ({noise:.0%} non-alphanumeric)")

    return result

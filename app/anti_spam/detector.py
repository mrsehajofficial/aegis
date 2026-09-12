""""""
detector.py — Anti-spam detector.

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

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://|www\.|t\.me/", re.IGNORECASE)
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


def count_urls(text: str) -> int:
    """Count URLs in text."""
    if not text:
        return 0
    return len(URL_PATTERN.findall(text))


def count_mentions(text: str) -> int:
    """Count @mentions in text."""
    if not text:
        return 0
    return len(MENTION_PATTERN.findall(text))"""

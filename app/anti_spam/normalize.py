"""
normalize.py — Text normalisation for spam matching.

Filters are trivially bypassed by changing how text *looks* rather than what it
says. This module collapses those tricks into one canonical form so that
matching sees through them:

* **Unicode NFKC** folds fullwidth and mathematical variants to ASCII, so
  "ｓｐａｍ" and "𝐬𝐩𝐚𝐦" both read as "spam".
* **Invisible characters are dropped.** Zero-width spaces are invisible but break
  naive substring checks: "s\\u200bpam" is not the string "spam".
* **Homoglyphs fold to Latin.** "раураl" (Cyrillic а, р, у) reads as "paypal".
* **Leetspeak folds inside words.** "fr33" becomes "free", but bare numbers,
  prices and phone numbers are left intact.
* **Repeated runs collapse** to two characters, so "freeeeee" reads as "free".

Caveat, stated plainly: folding is lossy and language-agnostic. A legitimate
Russian message is transformed into pseudo-Latin, so it could in principle
collide with an English banned word. That is the standard trade-off for
confusable folding, and it only ever affects *matching* — the original text is
what gets deleted or shown to admins, never the output of :func:`normalize`.
"""
import re
import unicodedata

# Zero-width and formatting characters: zero-width space/joiner/non-joiner, BOM,
# soft hyphen, word joiner, and Arabic letter mark.
_INVISIBLE = frozenset(
    "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\ufeff\u00ad\u180e"
)

# Combining marks used by "zalgo" text (U+0300 blocks and friends).
_COMBINING = re.compile(
    r"[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]"
)

# Cyrillic/Greek characters that render like Latin letters, plus a few
# mathematical forms NFKC leaves alone.
_HOMOGLYPHS = {
    "а": "a", "в": "b", "с": "c", "ԁ": "d", "е": "e", "ɡ": "g", "һ": "h",
    "і": "i", "ї": "i", "ј": "j", "к": "k", "ӏ": "l", "м": "m", "н": "h",
    "о": "o", "р": "p", "ԛ": "q", "ѕ": "s", "т": "t", "ѵ": "v", "ԝ": "w",
    "х": "x", "у": "y", "ь": "b", "з": "3", "б": "6",
    "α": "a", "β": "b", "γ": "y", "ε": "e", "ι": "i", "κ": "k", "μ": "m",
    "ν": "v", "ο": "o", "ρ": "p", "σ": "o", "τ": "t", "υ": "u", "χ": "x",
    "і": "i", "ⅰ": "i", "ⅼ": "l", "ⅽ": "c",
}

# Digits and symbols used as letter stand-ins.
_LEET = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t",
    "8": "b", "9": "g", "@": "a", "$": "s",
}

_TOKEN = re.compile(r"\S+")
_REPEATS = re.compile(r"(.)\1{2,}")


def _map_chars(text: str, table: dict) -> str:
    return "".join(table.get(ch, ch) for ch in text)


def strip_invisible(text: str) -> str:
    """Remove zero-width and formatting characters."""
    return "".join(ch for ch in text if ch not in _INVISIBLE)


def map_homoglyphs(text: str) -> str:
    """Fold Cyrillic/Greek look-alikes to Latin ('раураl' -> 'paypal')."""
    return _map_chars(text, _HOMOGLYPHS)


def fold_leet(text: str) -> str:
    """
    Fold digit/symbol substitutions inside words that contain letters.

    Only tokens with at least one letter are touched, so "1337", "$500" and
    "+1 555 0100" survive unchanged.
    """
    def _fold(match: re.Match) -> str:
        token = match.group(0)
        if any(ch.isalpha() for ch in token) and any(ch in _LEET for ch in token):
            return "".join(_LEET.get(ch, ch) for ch in token)
        return token

    return _TOKEN.sub(_fold, text)


def collapse_repeats(text: str) -> str:
    """Collapse runs of 3+ identical characters to two ("freeeeee" -> "free")."""
    return _REPEATS.sub(r"\1\1", text)


def normalize(text: str) -> str:
    """
    Return the canonical matching form of ``text``.

    Lossy by design: never display this, only match against it. The result is
    case-folded so callers can compare without lowercasing again.
    """
    if not text:
        return ""
    # NFKC first — it folds fullwidth and mathematical forms into ASCII, which
    # keeps the homoglyph table below small.
    flat = unicodedata.normalize("NFKC", text)
    flat = strip_invisible(flat)
    flat = map_homoglyphs(flat)
    flat = fold_leet(flat)
    flat = collapse_repeats(flat)
    return flat.casefold()


def combining_ratio(text: str) -> float:
    """Share of characters that are combining marks (zalgo text scores high)."""
    if not text:
        return 0.0
    return len(_COMBINING.findall(text)) / len(text)


def non_alphanumeric_ratio(text: str) -> float:
    """Share of non-space characters that are neither letters nor digits."""
    stripped = [ch for ch in text if not ch.isspace()]
    if not stripped:
        return 0.0
    noise = sum(1 for ch in stripped if not ch.isalnum())
    return noise / len(stripped)


def longest_repeat_run(text: str) -> int:
    """Length of the longest run of one repeated character."""
    best = run = 0
    previous = None
    for ch in text:
        run = run + 1 if ch == previous else 1
        previous = ch
        best = max(best, run)
    return best
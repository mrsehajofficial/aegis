"""Unit tests for the anti-spam detector heuristics."""
import pytest

from app.anti_spam.detector import (
    check_edited_spam,
    check_spam,
    check_text_abuse,
    count_mentions,
    count_urls,
)


class TestCountUrls:
    """count_urls must count links without double-counting or false positives."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("", 0),
            ("good morning everyone", 0),
            ("file.txt and e.g. a note", 0),
            ("https://example.com", 1),
            ("www.example.com", 1),
            ("t.me/somechannel", 1),
            ("bit.ly/abc123", 1),
            ("spam.ru", 1),
            ("HTTPS://EXAMPLE.COM/Path?q=1", 1),
            ("join bit.ly/x or spam.ru", 2),
        ],
    )
    def test_counts_links(self, text, expected):
        assert count_urls(text) == expected

    def test_scheme_qualified_link_is_not_double_counted(self):
        # Regression guard: a naive second bare-domain pass reports 2 here.
        assert count_urls("https://spam.ru") == 1
        assert count_urls("www.spam.ru") == 1


class TestCountMentions:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("", 0),
            ("hello world", 0),
            ("@ab", 0),  # shorter than Telegram's 5-character username minimum
            ("@abcde", 1),
            ("hi @alice and @bobby", 2),
        ],
    )
    def test_counts_mentions(self, text, expected):
        assert count_mentions(text) == expected


class TestCheckSpam:
    def test_clean_message_is_not_spam(self):
        result = check_spam("good morning everyone", url_count=0, mention_count=0)
        assert result.is_spam is False
        assert result.reasons == []

    def test_empty_text_is_never_spam(self):
        assert check_spam("").is_spam is False

    def test_caps_abuse_is_flagged(self):
        result = check_spam("THIS IS ALL CAPS SHOUTING", url_count=0, mention_count=0)
        assert result.is_spam is True
        assert "excessive caps" in result.reasons

    def test_url_flood_needs_three_links(self):
        assert check_spam("two links", url_count=2, mention_count=0).is_spam is False
        assert check_spam("three links", url_count=3, mention_count=0).is_spam is True

    def test_one_link_in_normal_chat_is_allowed(self):
        # A single link is ordinary conversation — only edits are strict.
        result = check_spam("see https://example.com", url_count=1, mention_count=0)
        assert result.is_spam is False

    def test_mention_flood_needs_five_mentions(self):
        assert check_spam("hi", url_count=0, mention_count=4).is_spam is False
        assert check_spam("hi", url_count=0, mention_count=5).is_spam is True

    def test_forwarded_message_with_body_text_is_flagged(self):
        result = check_spam("x" * 25, has_forward=True, url_count=0, mention_count=0)
        assert "frequent forwarding" in result.reasons


class TestCheckEditedSpam:
    """Edits are held to a stricter standard than ordinary messages."""

    def test_single_link_added_by_edit_is_spam(self):
        # The core behaviour: tolerated in a normal message, not in an edit.
        assert check_spam("new link here", False, 1, 0).is_spam is False
        result = check_edited_spam("new link here", False, 1, 0)
        assert result.is_spam is True
        assert any("edited message" in reason for reason in result.reasons)

    def test_mention_burst_added_by_edit_is_spam(self):
        result = check_edited_spam("hi", False, 0, 3)
        assert result.is_spam is True
        assert any("mention burst" in reason for reason in result.reasons)

    def test_single_mention_in_an_edit_is_allowed(self):
        assert check_edited_spam("thanks @alice", False, 0, 1).is_spam is False

    def test_edit_without_links_or_mentions_is_clean(self):
        assert check_edited_spam("fixed a typo", False, 0, 0).is_spam is False

    def test_edit_inherits_the_normal_checks(self):
        result = check_edited_spam("A" * 20, False, 0, 0)
        assert "excessive caps" in result.reasons


class TestCheckTextAbuse:
    """Structural signals that catch messages with no links and no banned words."""

    def test_plain_text_is_clean(self):
        assert check_text_abuse("good morning everyone").is_spam is False

    def test_empty_text_is_clean(self):
        assert check_text_abuse("").is_spam is False

    def test_ordinary_enthusiasm_passes(self):
        assert check_text_abuse("sooooo good!!!").is_spam is False

    def test_short_punctuation_is_not_a_symbol_flood(self):
        assert check_text_abuse("hi!!!").is_spam is False

    def test_zalgo_text_is_flagged(self):
        result = check_text_abuse("z" + "\u0301" * 8)
        assert result.is_spam is True
        assert any("zalgo" in reason for reason in result.reasons)

    def test_character_flood_is_flagged(self):
        result = check_text_abuse("aaaaaaaaaaaa")
        assert any("character flood" in reason for reason in result.reasons)

    def test_symbol_wall_is_flagged(self):
        result = check_text_abuse("!" * 28)
        assert any("symbol flood" in reason for reason in result.reasons)
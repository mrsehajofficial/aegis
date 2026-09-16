"""Tests for the spam-matching normalisation layer."""
import pytest

from app.anti_spam.normalize import (
    collapse_repeats,
    combining_ratio,
    fold_leet,
    longest_repeat_run,
    map_homoglyphs,
    non_alphanumeric_ratio,
    normalize,
    strip_invisible,
)


class TestStripInvisible:
    def test_removes_zero_width_characters(self):
        # "s<ZWSP>pam" looks identical to "spam" but is a different string.
        assert strip_invisible("s\u200bpam") == "spam"

    def test_removes_soft_hyphen_and_bom(self):
        assert strip_invisible("\ufeffsoft\u00adhyphen") == "softhyphen"

    def test_leaves_normal_text_alone(self):
        assert strip_invisible("hello world") == "hello world"


class TestHomoglyphs:
    def test_cyrillic_lookalikes_fold_to_latin(self):
        assert map_homoglyphs("раураl") == "paypal"

    def test_greek_lookalikes_fold(self):
        assert map_homoglyphs("αο") == "ao"

    def test_plain_ascii_is_untouched(self):
        assert map_homoglyphs("transfer") == "transfer"


class TestLeetFolding:
    def test_folds_digits_inside_words(self):
        assert fold_leet("fr33") == "free"

    @pytest.mark.parametrize("token", ["1337", "$500", "+1 555 0100", "12345"])
    def test_leaves_bare_numbers_alone(self, token):
        assert fold_leet(token) == token


class TestCollapseRepeats:
    def test_collapses_long_runs(self):
        assert collapse_repeats("freeeeee") == "free"

    def test_keeps_short_runs(self):
        assert collapse_repeats("cool") == "cool"


class TestMetrics:
    def test_combined_ratio_of_plain_text(self):
        assert combining_ratio("hello") == 0.0

    def test_combining_ratio_of_zalgo_text(self):
        assert combining_ratio("a" + "\u0301" * 6) > 0.8

    def test_non_alphanumeric_ratio_of_a_sentence(self):
        assert non_alphanumeric_ratio("hello world") == 0.0

    def test_non_alphanumeric_ratio_of_symbols(self):
        assert non_alphanumeric_ratio("!!!!!") == 1.0

    def test_non_alphanumeric_ratio_of_empty_text(self):
        assert non_alphanumeric_ratio("") == 0.0

    @pytest.mark.parametrize(
        "text, expected",
        [("", 0), ("abc", 1), ("aabb", 2), ("aaaaa", 5)],
    )
    def test_longest_repeat_run(self, text, expected):
        assert longest_repeat_run(text) == expected


class TestNormalize:
    def test_defeats_invisible_character_evasion(self):
        assert "spam" in normalize("s\u200bpam")

    def test_defeats_homoglyph_evasion(self):
        assert "paypal" in normalize("раураl")

    def test_defeats_leetspeak_evasion(self):
        assert "free" in normalize("fr33")

    def test_defeats_repeat_evasion(self):
        assert "spam" in normalize("spammmmm")

    def test_defeats_fullwidth_evasion(self):
        # NFKC folds fullwidth letters to ASCII.
        assert "spam" in normalize("ｓｐａｍ")

    def test_result_is_casefolded(self):
        assert normalize("SPAM") == "spam"

    def test_empty_input(self):
        assert normalize("") == ""

    def test_ordinary_text_is_preserved(self):
        assert normalize("good morning everyone") == "good morning everyone"

class TestUppercaseHomoglyphEvasion:
    """Regression: case-folding must precede homoglyph mapping.

    The homoglyph table only carries lowercase look-alikes, so a capital
    Cyrillic А used to survive normalisation and dodge every match.
    """

    def test_capital_cyrillic_a_folds_to_latin(self):
        assert "channel" in normalize("CH\u0410NNEL")

    def test_capital_cyrillic_e_folds_to_latin(self):
        assert "free" in normalize("FR\u0415\u0415")

    def test_mixed_case_homoglyph_attack_matches_plain_text(self):
        from app.anti_spam.reputation import fingerprint

        assert fingerprint("JOIN MY CH\u0410NNEL") == fingerprint("join my channel")

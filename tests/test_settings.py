"""Unit tests for configuration parsing."""
import pytest

from app.config.settings import Settings


class TestSuperAdminIds:
    """SUPER_ADMIN_IDS accepts the many shapes admins actually paste in."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            (None, []),
            ("", []),
            ("[]", []),
            (12345, [12345]),
            ("12345", [12345]),
            ("1,2,3", [1, 2, 3]),
            ("1, 2, 3", [1, 2, 3]),
            ("[1,2]", [1, 2]),
            ([1, 2], [1, 2]),
            (" 7 ", [7]),
        ],
    )
    def test_parses_common_formats(self, raw, expected):
        assert Settings(SUPER_ADMIN_IDS=raw).SUPER_ADMIN_IDS == expected


class TestDefaults:
    def test_bot_name_default_is_aegis(self):
        # Field default, independent of any local .env override.
        assert Settings.model_fields["BOT_NAME"].default == "Aegis"

    def test_warn_action_default_is_a_documented_choice(self):
        assert Settings.model_fields["WARN_ACTION"].default in {"mute", "ban", "kick"}

    def test_database_url_default_is_local_sqlite(self):
        assert Settings.model_fields["DATABASE_URL"].default.startswith("sqlite")

    def test_reputation_feed_url_defaults_to_empty(self):
        assert Settings.model_fields["REPUTATION_FEED_URL"].default == ""

    def test_reputation_salt_defaults_to_empty(self):
        assert Settings.model_fields["REPUTATION_SALT"].default == ""
"""
tests for welcome/goodbye message functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Chat, User, ChatMember

from app.bot.handlers.welcome import (
    _send_join_or_leave_message,
    handle_chat_member,
    _display_name,
    _render_template,
)
from app.database.models.settings import GroupSettings


class TestDisplayName:
    """Tests for the _display_name helper."""

    def test_none_returns_friend(self):
        assert _display_name(None) == "friend"

    def test_ptb_user_full_name(self):
        user = User(id=123, first_name="Alice", is_bot=False)
        assert _display_name(user) == "Alice"

    def test_ptb_user_username_fallback(self):
        user = User(id=123, first_name="", username="alice_bot", is_bot=False)
        assert _display_name(user) == "alice_bot"

    def test_ptb_user_id_fallback(self):
        user = User(id=123, first_name="", username=None, is_bot=False)
        assert _display_name(user) == "123"


def make_mock_settings(**overrides):
    """Create a mock GroupSettings with sensible defaults."""
    defaults = dict(
        group_id=1,
        welcome_enabled=True,
        goodbye_enabled=True,
        anti_flood_enabled=False,
        anti_spam_enabled=False,
        log_enabled=False,
        reports_enabled=True,
        warn_limit=3,
        flood_msg_limit=5,
        flood_window_seconds=3.0,
        flood_mute_minutes=5,
        spam_action="delete",
        captcha_enabled=False,
        captcha_timeout_seconds=120,
        captcha_action="kick",
    )
    defaults.update(overrides)
    return GroupSettings(**defaults)


def make_mock_group(**overrides):
    """Create a mock Group."""
    mock = MagicMock()
    mock.id = 1
    mock.telegram_id = -100123
    mock.title = "Test Group"
    for k, v in overrides.items():
        setattr(mock, k, v)
    return mock


class TestSendJoinOrLeave:
    """Tests for _send_join_or_leave_message."""

    @pytest.mark.asyncio
    async def test_sends_default_template_when_enabled(self):
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock()

        mock_group = make_mock_group()
        mock_settings = make_mock_settings(welcome_enabled=True, goodbye_enabled=True)

        # Properly mock the database session and repositories
        mock_session = AsyncMock()

        mock_group_repo = MagicMock()
        mock_group_repo.get_by_telegram_id = AsyncMock(return_value=mock_group)

        mock_settings_repo = MagicMock()
        mock_settings_repo.get_or_create = AsyncMock(return_value=mock_settings)

        # Patch the actual usage in welcome.py: get_session() and GroupRepository(session)
        with patch("app.bot.handlers.welcome.get_session") as mock_get_session:
            # get_session() returns an async context manager
            mock_get_session.return_value.__aenter__.return_value = mock_session
            # GroupRepository(session) returns our mock
            with patch("app.bot.handlers.welcome.GroupRepository", return_value=mock_group_repo):
                with patch("app.bot.handlers.welcome.SettingsRepository", return_value=mock_settings_repo):
                    sent = await _send_join_or_leave_message(mock_bot, -100123, "welcome", ["Alice"])

        assert sent is True
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert "Alice" in call_args.kwargs["text"]
        assert "Test Group" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_sends_custom_message(self):
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock()

        mock_group = make_mock_group()
        mock_settings = make_mock_settings(
            welcome_enabled=True,
            goodbye_enabled=True,
            welcome_message="Custom welcome: {name} to {group}!",
        )

        mock_session = AsyncMock()
        mock_group_repo = MagicMock()
        mock_group_repo.get_by_telegram_id = AsyncMock(return_value=mock_group)
        mock_settings_repo = MagicMock()
        mock_settings_repo.get_or_create = AsyncMock(return_value=mock_settings)

        with patch("app.bot.handlers.welcome.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            with patch("app.bot.handlers.welcome.GroupRepository", return_value=mock_group_repo):
                with patch("app.bot.handlers.welcome.SettingsRepository", return_value=mock_settings_repo):
                    sent = await _send_join_or_leave_message(mock_bot, -100123, "welcome", ["Eve"])

        assert sent is True
        call_args = mock_bot.send_message.call_args
        assert "Custom welcome: Eve to Test Group!" in call_args.kwargs["text"]

    def test_multiple_names_are_joined(self):
        result = _render_template(
            "Welcome {name}!",
            name=", ".join(["Alice", "Bob"]),
        )
        assert "Alice, Bob" in result

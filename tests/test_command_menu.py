"""
Tests for the Telegram command menu, onboarding copy and menu keyboard.

These lock in the Phase 1 usability work: commands must be valid for Telegram's
menu, and the /start keyboard must stay in sync with the callback router.
"""
import re
from unittest.mock import AsyncMock, MagicMock

from app.bot.application import _COMMANDS, _GROUP_COMMANDS
from app.bot.handlers.commands import _format_uptime, _latency_dot, build_help_text
from app.bot.handlers.start import build_menu, build_start_text, menu_callback


class TestCommandMenu:
    def test_command_names_are_unique(self):
        names = [c.command for c in _COMMANDS]
        assert len(names) == len(set(names))

    def test_names_follow_telegram_rules(self):
        # Telegram allows 1-32 chars: lowercase letters, digits and underscores.
        for command in _COMMANDS:
            assert 1 <= len(command.command) <= 32
            assert re.fullmatch(r"[a-z0-9_]+", command.command), command.command

    def test_descriptions_follow_telegram_limits(self):
        # Telegram requires 3-256 characters.
        for command in _COMMANDS:
            assert 3 <= len(command.description) <= 256, command.command

    def test_start_help_and_ping_are_advertised(self):
        names = {c.command for c in _COMMANDS}
        assert {"start", "help", "ping"} <= names

    def test_group_scope_only_drops_start(self):
        group_names = {c.command for c in _GROUP_COMMANDS}
        assert group_names == {c.command for c in _COMMANDS} - {"start"}


class TestHelpText:
    def test_lists_the_core_commands(self):
        text = build_help_text()
        for command in ("/ban", "/mute", "/warn", "/purge", "/filter", "/save", "/logs"):
            assert command in text

    def test_is_usable_html(self):
        text = build_help_text()
        assert text.strip()
        assert text.count("<b>") == text.count("</b>")


class TestStartText:
    def test_private_and_group_copy_differ(self):
        assert build_start_text(is_group=True) != build_start_text(is_group=False)

    def test_group_copy_mentions_the_admin_upgrade(self):
        assert "admin" in build_start_text(is_group=True).lower()

    def test_private_copy_pitches_the_feature_set(self):
        text = build_start_text(is_group=False).lower()
        assert "moderation" in text
        assert "protection" in text


class TestStartMenu:
    def test_private_menu_offers_the_group_deep_link(self):
        markup = build_menu(is_group=False, bot_username="aegis_bot")
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        assert urls == ["https://t.me/aegis_bot?startgroup=true"]

    def test_group_menu_has_no_deep_link(self):
        # ?startgroup links are only valid in private chats.
        markup = build_menu(is_group=True, bot_username="aegis_bot")
        assert all(b.url is None for row in markup.inline_keyboard for b in row)

    def test_menu_omits_the_deep_link_without_a_username(self):
        markup = build_menu(is_group=False, bot_username=None)
        assert all(b.url is None for row in markup.inline_keyboard for b in row)

    def test_sub_screens_can_return_to_the_landing_screen(self):
        markup = build_menu(is_group=False, bot_username="aegis_bot", back_to_start=True)
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "menu:start" in data
        assert "menu:close" in data

    def test_every_button_matches_the_callback_handler_pattern(self):
        # The handler is registered for ^menu: — callback data must stay in sync.
        markups = (
            build_menu(is_group=False, bot_username="aegis_bot"),
            build_menu(is_group=True, bot_username="aegis_bot"),
            build_menu(is_group=False, bot_username=None, back_to_start=True),
        )
        for markup in markups:
            for row in markup.inline_keyboard:
                for button in row:
                    data = button.callback_data
                    assert data is None or data.startswith("menu:")

    def test_landing_menu_offers_commands_and_ping(self):
        markup = build_menu(is_group=True, bot_username="aegis_bot")
        data = {b.callback_data for row in markup.inline_keyboard for b in row}
        assert {"menu:help", "menu:ping"} <= data


class TestPingFormatting:
    def test_uptime_formatting(self):
        assert _format_uptime(0) == "0m 0s"
        assert _format_uptime(59) == "0m 59s"
        assert _format_uptime(60) == "1m 0s"
        assert _format_uptime(3661) == "1h 1m 1s"
        assert _format_uptime(90061) == "1d 1h 1m"

    def test_latency_indicator_is_never_blank(self):
        # Regression guard: the indicators used to be stripped to empty strings.
        for value in (10, 200, 500, 5000):
            assert _latency_dot(value).strip()

    def test_latency_indicator_reacts_to_speed(self):
        assert _latency_dot(10) == _latency_dot(200)  # both fast
        assert _latency_dot(10) != _latency_dot(5000)  # fast vs slow


class TestMenuCallbackRouting:
    """The callback router must acknowledge the tap, then render the right screen."""

    @staticmethod
    def _update(data: str):
        query = MagicMock()
        query.data = data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.chat.id = -100123
        query.message.delete = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        return update, query

    @staticmethod
    def _context():
        context = MagicMock()
        context.bot.username = "aegis_bot"
        context.bot.get_me = AsyncMock()
        context.bot.send_message = AsyncMock()
        return context

    async def test_close_deletes_the_menu_message(self):
        update, query = self._update("menu:close")
        await menu_callback(update, self._context())
        query.answer.assert_awaited()
        query.message.delete.assert_awaited()
        query.edit_message_text.assert_not_awaited()

    async def test_help_renders_the_reference_with_a_back_button(self):
        update, query = self._update("menu:help")
        await menu_callback(update, self._context())
        text = query.edit_message_text.call_args.args[0]
        markup = query.edit_message_text.call_args.kwargs["reply_markup"]
        assert "/ban" in text
        assert any(
            button.callback_data == "menu:start"
            for row in markup.inline_keyboard
            for button in row
        )

    async def test_ping_renders_a_latency_report(self):
        update, query = self._update("menu:ping")
        await menu_callback(update, self._context())
        text = query.edit_message_text.call_args.args[0]
        assert "Pong" in text
        assert "Uptime" in text

    async def test_unknown_action_returns_to_the_landing_screen(self):
        update, query = self._update("menu:not-a-real-action")
        await menu_callback(update, self._context())
        text = query.edit_message_text.call_args.args[0]
        assert "Aegis" in text

    async def test_a_failed_edit_falls_back_to_a_new_message(self):
        update, query = self._update("menu:help")
        query.edit_message_text.side_effect = RuntimeError("message can't be edited")
        context = self._context()
        await menu_callback(update, context)
        context.bot.send_message.assert_awaited()

    async def test_an_unchanged_screen_is_not_re_sent(self):
        update, query = self._update("menu:start")
        query.edit_message_text.side_effect = RuntimeError("Message is not modified")
        context = self._context()
        await menu_callback(update, context)
        # Telegram rejects no-op edits; we must not spam the chat with a duplicate.
        context.bot.send_message.assert_not_awaited()
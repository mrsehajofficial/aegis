"""
Tests for the welcome/goodbye system: message rendering, the shared
join/leave sender, and the chat-member handler.

The handler tests follow the same pattern as tests/test_core.py: they run
against the configured SQLite database via init_db()/get_session().
"""
import asyncio
from types import SimpleNamespace

import pytest
from telegram import Chat, User

from app.config.settings import settings
from app.database.connection import get_session, init_db, close_db
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.bot.handlers.welcome import (
    _display_name,
    _render_template,
    _send_join_or_leave_message,
    handle_chat_member,
    DEFAULT_WELCOME_MESSAGE,
    DEFAULT_GOODBYE_MESSAGE,
)


class FakeBot:
    """Minimal stand-in for context.bot that records sent messages."""

    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, parse_mode=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})


class TestRenderTemplate:
    def test_substitutes_placeholders(self):
        out = _render_template("Hi {name} in {group}!", name="Alice", group="TG")
        assert out == "Hi Alice in TG!"

    def test_ignores_unknown_placeholders(self):
        out = _render_template("Hi {name}!", name="Bob")
        assert out == "Hi Bob!"

    def test_supports_braces_in_custom_templates(self):
        # str.format would choke on {name} {"x": 1}; .replace() must not.
        out = _render_template("Hi {name}, dict={'a': 1}", name="Bob")
        assert out == "Hi Bob, dict={'a': 1}"

    def test_none_template_renders_empty(self):
        assert _render_template(None, name="Bob") == ""


class TestDisplayName:
    def test_ptb_user_full_name(self):
        u = User(id=10, first_name="Alice", is_bot=False, last_name="Smith")
        assert _display_name(u) == "Alice Smith"

    def test_ptb_user_username_fallback(self):
        u = User(id=11, first_name="", is_bot=True, username="coolbot")
        assert _display_name(u) == "coolbot"

    def test_ptb_user_id_fallback(self):
        u = User(id=12, first_name="", is_bot=False)
        assert _display_name(u) == "12"

    def test_none_returns_friend(self):
        assert _display_name(None) == "friend"


class TestSendJoinOrLeave:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    async def _make_group(self, telegram_id, title, **settings_kwargs):
        await init_db()
        async with get_session() as session:
            group = await GroupRepository(session).upsert_group(
                telegram_id=telegram_id, title=title, type_="supergroup"
            )
            await SettingsRepository(session).update(group.id, **settings_kwargs)
            await session.commit()
        return group

    async def test_skips_when_disabled(self):
        await self._make_group(900_001, "TG Disabled", welcome_enabled=False)
        bot = FakeBot()
        sent = await _send_join_or_leave_message(bot, 900_001, "welcome", ["Alice"])
        assert sent is False
        assert bot.sent == []

    async def test_sends_default_template_when_enabled(self):
        await self._make_group(900_002, "TG Default", welcome_enabled=True)
        bot = FakeBot()
        sent = await _send_join_or_leave_message(bot, 900_002, "welcome", ["Alice"])
        assert sent is True
        assert len(bot.sent) == 1
        text = bot.sent[0]["text"]
        assert "Welcome to TG Default, Alice!" in text

    async def test_sends_custom_message(self):
        await self._make_group(
            900_003, "TG Custom", welcome_enabled=True,
            welcome_message="Hey {name}, welcome to {group} from {bot}!",
        )
        bot = FakeBot()
        sent = await _send_join_or_leave_message(bot, 900_003, "welcome", ["Alice"])
        assert sent is True
        expected = f"Hey Alice, welcome to TG Custom from {settings.BOT_NAME}!"
        assert bot.sent[0]["text"] == expected

    async def test_goodbye_respects_flag(self):
        await self._make_group(900_004, "TG Bye", goodbye_enabled=True)
        bot = FakeBot()
        sent = await _send_join_or_leave_message(bot, 900_004, "goodbye", ["Bob"])
        assert sent is True
        assert "Bob" in bot.sent[0]["text"]

    async def test_unregistered_group_returns_false(self):
        bot = FakeBot()
        sent = await _send_join_or_leave_message(bot, 900_111, "welcome", ["Alice"])
        assert sent is False
        assert bot.sent == []

    async def test_multiple_names_are_joined(self):
        await self._make_group(900_005, "TG Multi", welcome_enabled=True)
        bot = FakeBot()
        await _send_join_or_leave_message(bot, 900_005, "welcome", ["Alice", "Bob"])
        assert "Alice, Bob" in bot.sent[0]["text"]


class TestHandleChatMember:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    @staticmethod
    def _chat_member(status):
        return SimpleNamespace(status=status)

    def _make_update(self, chat, user, old, new):
        return SimpleNamespace(
            chat_member=SimpleNamespace(
                chat=chat,
                user=user,
                old_chat_member=self._chat_member(old),
                new_chat_member=self._chat_member(new),
            )
        )

    async def test_join_sends_welcome(self):
        await init_db()
        tg_id = 900_010
        async with get_session() as session:
            group = await GroupRepository(session).upsert_group(
                telegram_id=tg_id, title="TG Join", type_="supergroup"
            )
            await SettingsRepository(session).update(group.id, welcome_enabled=True)
            await session.commit()

        chat = Chat(id=tg_id, type=Chat.SUPERGROUP, title="TG Join")
        user = User(id=100, first_name="Alice", is_bot=False)
        bot = FakeBot()
        update = self._make_update(chat, user, "left", "member")
        await handle_chat_member(update, SimpleNamespace(bot=bot))
        assert len(bot.sent) == 1
        assert "Alice" in bot.sent[0]["text"]

    async def test_join_of_bot_also_sends_welcome(self):
        await init_db()
        tg_id = 900_011
        async with get_session() as session:
            group = await GroupRepository(session).upsert_group(
                telegram_id=tg_id, title="TG Bot Join", type_="supergroup"
            )
            await SettingsRepository(session).update(group.id, welcome_enabled=True)
            await session.commit()

        chat = Chat(id=tg_id, type=Chat.SUPERGROUP, title="TG Bot Join")
        bot_user = User(id=101, first_name="", is_bot=True, username="otherbot")
        bot = FakeBot()
        update = self._make_update(chat, bot_user, "left", "member")
        await handle_chat_member(update, SimpleNamespace(bot=bot))
        assert len(bot.sent) == 1
        assert "otherbot" in bot.sent[0]["text"]

    async def test_leave_sends_goodbye_only_if_enabled(self):
        await init_db()
        tg_id = 900_012
        async with get_session() as session:
            group = await GroupRepository(session).upsert_group(
                telegram_id=tg_id, title="TG Leave", type_="supergroup"
            )
            await SettingsRepository(session).update(group.id, goodbye_enabled=True)
            await session.commit()

        chat = Chat(id=tg_id, type=Chat.SUPERGROUP, title="TG Leave")
        user = User(id=102, first_name="Bob", is_bot=False)
        bot = FakeBot()
        update = self._make_update(chat, user, "member", "left")
        await handle_chat_member(update, SimpleNamespace(bot=bot))
        assert len(bot.sent) == 1
        assert "Bob" in bot.sent[0]["text"]

    async def test_leave_with_disabled_goodbye_sends_nothing(self):
        await init_db()
        tg_id = 900_013
        async with get_session() as session:
            group = await GroupRepository(session).upsert_group(
                telegram_id=tg_id, title="TG Leave Off", type_="supergroup"
            )
            await SettingsRepository(session).update(group.id, goodbye_enabled=False)
            await session.commit()

        chat = Chat(id=tg_id, type=Chat.SUPERGROUP, title="TG Leave Off")
        user = User(id=103, first_name="Bob", is_bot=False)
        bot = FakeBot()
        update = self._make_update(chat, user, "member", "kicked")
        await handle_chat_member(update, SimpleNamespace(bot=bot))
        assert bot.sent == []

    async def test_non_group_chat_is_ignored(self):
        await init_db()
        bot = FakeBot()
        chat = Chat(id=77, type=Chat.PRIVATE, title=None)
        user = User(id=104, first_name="Eve", is_bot=False)
        update = self._make_update(chat, user, "left", "member")
        await handle_chat_member(update, SimpleNamespace(bot=bot))
        assert bot.sent == []

    def test_default_templates_reference_expected_placeholders(self):
        assert "{name}" in DEFAULT_WELCOME_MESSAGE and "{group}" in DEFAULT_WELCOME_MESSAGE
        assert "{name}" in DEFAULT_GOODBYE_MESSAGE and "{group}" in DEFAULT_GOODBYE_MESSAGE
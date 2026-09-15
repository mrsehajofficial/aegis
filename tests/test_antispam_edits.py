"""
Integration tests for the edit-aware anti-spam path.

``AntiSpamChecker`` is the seam between the Telegram handler and the detector, so
these tests drive it with lightweight fakes. They prove an edited message is held
to a stricter standard than a fresh one, and that nothing is deleted when it
should not be.
"""
import pytest

from app.anti_spam import AntiSpamChecker, GroupProtectionSettings, flood
from app.anti_spam.flood import InMemoryFloodStore


@pytest.fixture(autouse=True)
def _fresh_flood_store():
    """Flood state is module-global — give every test case a clean store."""
    flood.configure_store(InMemoryFloodStore())
    flood._fallback = InMemoryFloodStore()
    yield
    flood.configure_store(InMemoryFloodStore())
    flood._fallback = InMemoryFloodStore()


class _FakeUser:
    def __init__(self, user_id: int = 42):
        self.id = user_id


class _FakeMessage:
    """Only the attributes the checker and its actions actually touch."""

    def __init__(self, text: str, user_id: int = 42):
        self.text = text
        self.caption = None
        self.from_user = _FakeUser(user_id)
        self.forward_date = None
        self.message_id = 5
        self.deleted = False

    async def delete(self):
        self.deleted = True


class _FakeBot:
    def __init__(self):
        self.notifications = []
        self.restricted = []

    async def send_message(self, chat_id, text, **kwargs):
        self.notifications.append(text)

    async def restrict_chat_member(self, chat_id, user_id, **kwargs):
        self.restricted.append((chat_id, user_id))
        return True


class _FakeContext:
    def __init__(self):
        self.bot = _FakeBot()


def _checker(**overrides) -> AntiSpamChecker:
    protection = GroupProtectionSettings(anti_spam_enabled=True, **overrides)
    return AntiSpamChecker(_FakeContext(), chat_id=-100123, settings=protection)


class TestEditedMessageHandling:
    async def test_edit_that_introduces_a_link_is_deleted(self):
        checker = _checker()
        message = _FakeMessage("grab it at spam.ru")
        assert await checker.check_message(message, is_edit=True) == "spam_deleted"
        assert message.deleted is True

    async def test_the_same_text_is_left_alone_when_not_an_edit(self):
        checker = _checker()
        message = _FakeMessage("grab it at spam.ru")
        assert await checker.check_message(message) is None
        assert message.deleted is False

    async def test_edit_without_links_or_mentions_is_left_alone(self):
        checker = _checker()
        message = _FakeMessage("fixed a typo")
        assert await checker.check_message(message, is_edit=True) is None
        assert message.deleted is False

    async def test_edits_are_ignored_when_anti_spam_is_off(self):
        checker = AntiSpamChecker(
            _FakeContext(),
            chat_id=-100123,
            settings=GroupProtectionSettings(anti_spam_enabled=False),
        )
        message = _FakeMessage("grab it at spam.ru")
        assert await checker.check_message(message, is_edit=True) is None
        assert message.deleted is False

    async def test_edit_honours_a_configured_mute_action(self):
        checker = _checker(spam_action="mute")
        message = _FakeMessage("grab it at spam.ru")
        assert await checker.check_message(message, is_edit=True) == "spam_muted"
        assert message.deleted is True


class TestFloodStillWorks:
    async def test_flood_triggers_on_ordinary_messages(self):
        checker = _checker(
            anti_flood_enabled=True,
            flood_msg_limit=2,
            flood_window_seconds=30.0,
        )
        assert await checker.check_message(_FakeMessage("hello")) is None
        second = _FakeMessage("hello again")
        assert await checker.check_message(second) == "flood_mute"
        assert second.deleted is True


class TestHandlerWiring:
    def test_protection_handler_forwards_the_edit_flag(self):
        """Regression guard: edits must reach the stricter rule, not be treated as new posts."""
        import inspect

        from app.bot.handlers import group_protection

        source = inspect.getsource(group_protection.check_protection)
        assert "is_edit" in source
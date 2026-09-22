"""
Tests for Telegram Business chat automation and messaging on behalf of user.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from telegram import (
    Update,
    User,
    Chat,
    Message,
    BusinessConnection,
    BusinessBotRights,
)

from app.database.models.business import BusinessConnection as DBBusinessConnection, BusinessRule
from app.database.repositories.business import BusinessRepository
from app.services.business import (
    register_business_connection,
    get_business_connection_for_user,
    get_business_connection_by_id,
    toggle_auto_reply,
    toggle_greeting,
    toggle_away,
    set_greeting_message,
    set_away_message,
    add_business_rule,
    delete_business_rule,
    get_business_rules,
    evaluate_business_message,
    AWAY_MESSAGE_COOLDOWN_SEC,
    _chat_last_reply,
    _chat_last_away,
    _greeted_chats,
)
from app.bot.handlers.business import (
    handle_business_connection,
    handle_business_message,
    business_command,
    biz_callback,
    bizrules_command,
    bizadd_command,
    bizdel_command,
    bizgreeting_command,
    bizaway_command,
    bizstatus_command,
)


@pytest.fixture(autouse=True)
def reset_business_cache():
    """Clear in-memory debounce caches before each test."""
    _chat_last_reply.clear()
    _chat_last_away.clear()
    _greeted_chats.clear()
    yield
    _chat_last_reply.clear()
    _chat_last_away.clear()
    _greeted_chats.clear()


# ── Repository Tests ──────────────────────────────────────────────────────────


class TestBusinessRepository:
    async def test_upsert_and_get_connection(self, db_session):
        repo = BusinessRepository(db_session)

        # 1. Insert
        conn = await repo.upsert_connection(
            connection_id="biz_conn_123",
            user_id=1001,
            user_chat_id=1001,
            can_reply=True,
            is_enabled=True,
        )
        assert conn.connection_id == "biz_conn_123"
        assert conn.user_id == 1001
        assert conn.can_reply is True
        assert conn.is_enabled is True
        assert conn.auto_reply_enabled is True

        # 2. Query
        by_id = await repo.get_connection_by_id("biz_conn_123")
        assert by_id is not None
        assert by_id.user_id == 1001

        by_user = await repo.get_connection_by_user_id(1001)
        assert by_user is not None
        assert by_user.connection_id == "biz_conn_123"

        # 3. Update existing
        updated = await repo.upsert_connection(
            connection_id="biz_conn_123",
            user_id=1001,
            user_chat_id=1001,
            can_reply=False,
            is_enabled=False,
        )
        assert updated.can_reply is False
        assert updated.is_enabled is False

    async def test_rules_crud(self, db_session):
        repo = BusinessRepository(db_session)
        await repo.upsert_connection("c1", user_id=2001, user_chat_id=2001, can_reply=True, is_enabled=True)

        # Add rules
        r1 = await repo.add_or_update_rule(
            user_id=2001,
            trigger="Pricing",
            response="Pricing starts at $99",
            match_type="contains",
            connection_id="c1",
        )
        assert r1.trigger == "pricing"
        assert r1.response == "Pricing starts at $99"

        r2 = await repo.add_or_update_rule(
            user_id=2001,
            trigger="help",
            response="Contact support",
            match_type="exact",
            connection_id="c1",
        )
        assert r2.trigger == "help"

        # List rules
        rules = await repo.get_rules(user_id=2001)
        assert len(rules) == 2
        triggers = [r.trigger for r in rules]
        assert "pricing" in triggers
        assert "help" in triggers

        # Update rule
        r1_updated = await repo.add_or_update_rule(
            user_id=2001,
            trigger="pricing",
            response="Updated pricing: $149",
        )
        assert r1_updated.response == "Updated pricing: $149"

        # Delete rule
        deleted = await repo.delete_rule(user_id=2001, trigger="help")
        assert deleted is True

        remaining = await repo.get_rules(user_id=2001)
        assert len(remaining) == 1
        assert remaining[0].trigger == "pricing"


# ── Service Layer Tests ───────────────────────────────────────────────────────


class TestBusinessService:
    async def test_register_connection_seeds_defaults(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            conn = await register_business_connection(
                connection_id="biz_seed_test",
                user_id=3001,
                user_chat_id=3001,
                can_reply=True,
                is_enabled=True,
            )
            assert conn.connection_id == "biz_seed_test"

            rules = await get_business_rules(3001)
            assert len(rules) == 4
            triggers = {r.trigger for r in rules}
            assert {"price", "hours", "support", "hello"} <= triggers

    async def test_toggles_and_message_setters(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("c2", user_id=4001, user_chat_id=4001, can_reply=True, is_enabled=True)

            # Toggle auto reply
            new_ar = await toggle_auto_reply(4001)
            assert new_ar is False
            new_ar = await toggle_auto_reply(4001)
            assert new_ar is True

            # Greeting
            assert await toggle_greeting(4001) is True
            assert await set_greeting_message(4001, "Welcome to my store!") is True
            conn = await get_business_connection_for_user(4001)
            assert conn.greeting_message == "Welcome to my store!"
            assert conn.greeting_enabled is True

            # Away
            assert await toggle_away(4001) is True
            assert await set_away_message(4001, "Currently out of office.") is True
            conn = await get_business_connection_for_user(4001)
            assert conn.away_message == "Currently out of office."
            assert conn.away_enabled is True

    async def test_evaluate_business_message_rules(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("c3", user_id=5001, user_chat_id=5001, can_reply=True, is_enabled=True)
            await add_business_rule(5001, "quote", "Quotes are provided within 24 hours.", match_type="contains")
            await add_business_rule(5001, "status", "All systems operational.", match_type="exact")

            # 1. Substring / contains match
            reply = await evaluate_business_message(
                connection_id="c3",
                chat_id=999,
                from_user_id=777,
                text="Hi, can I get a quote for a website?",
            )
            assert reply == "Quotes are provided within 24 hours."

            # Clear debounce for next test
            _chat_last_reply.clear()

            # 2. Exact match success
            reply = await evaluate_business_message(
                connection_id="c3",
                chat_id=999,
                from_user_id=777,
                text="status",
            )
            assert reply == "All systems operational."

            _chat_last_reply.clear()

            # 3. Exact match failure when surrounded by other words
            reply = await evaluate_business_message(
                connection_id="c3",
                chat_id=999,
                from_user_id=777,
                text="what is the status please?",
            )
            assert reply is None

    async def test_evaluate_ignores_owner_messages(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("c4", user_id=6001, user_chat_id=6001, can_reply=True, is_enabled=True)
            await add_business_rule(6001, "price", "$50")

            # Sender is the owner (user_id 6001)
            reply = await evaluate_business_message(
                connection_id="c4",
                chat_id=888,
                from_user_id=6001,
                text="The price is listed here",
            )
            assert reply is None

    async def test_evaluate_respects_auto_reply_disabled(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("c5", user_id=7001, user_chat_id=7001, can_reply=True, is_enabled=True)
            await add_business_rule(7001, "hello", "Hello!")
            await toggle_auto_reply(7001)  # disabled

            reply = await evaluate_business_message(
                connection_id="c5",
                chat_id=888,
                from_user_id=999,
                text="hello",
            )
            assert reply is None

    async def test_evaluate_greeting_and_away_fallback(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("c6", user_id=8001, user_chat_id=8001, can_reply=True, is_enabled=True)
            await set_greeting_message(8001, "Hi! Welcome.")
            await set_away_message(8001, "I am away right now.")

            # Drive the cooldowns with an injected clock whose uptime is small.
            # A fresh machine — a CI runner, a fresh container, a rebooted host —
            # reports time.monotonic() as seconds since boot, so "never sent"
            # must not be modelled as a timestamp of 0.0: at an uptime of 30s
            # that read as a reply 30s ago and silenced the away fallback.
            now = 30.0

            # First message that matches no keywords triggers greeting
            reply = await evaluate_business_message(
                connection_id="c6",
                chat_id=111,
                from_user_id=222,
                text="Random question without keywords",
                now=now,
            )
            assert reply == "Hi! Welcome."

            # Second message: chat already greeted, so the away fallback answers
            # (the 2s reply debounce has passed, and no away message has been
            # sent yet, so the 15-minute cooldown does not apply)
            reply2 = await evaluate_business_message(
                connection_id="c6",
                chat_id=111,
                from_user_id=222,
                text="Another unrecognized question",
                now=now + 3.0,
            )
            assert reply2 == "I am away right now."

            # A third unrecognized message inside the away cooldown stays
            # unanswered instead of replying to every single message
            reply3 = await evaluate_business_message(
                connection_id="c6",
                chat_id=111,
                from_user_id=222,
                text="Still waiting for a reply",
                now=now + 60.0,
            )
            assert reply3 is None

            # Once the cooldown elapses the fallback may answer again
            reply4 = await evaluate_business_message(
                connection_id="c6",
                chat_id=111,
                from_user_id=222,
                text="Are you there?",
                now=now + 3.0 + AWAY_MESSAGE_COOLDOWN_SEC,
            )
            assert reply4 == "I am away right now."


# ── Handler Tests ─────────────────────────────────────────────────────────────


class TestBusinessHandlers:
    @staticmethod
    def _context():
        ctx = MagicMock()
        ctx.bot.username = "aegis_bot"
        ctx.bot.send_message = AsyncMock()
        return ctx

    async def test_handle_business_connection_enabled(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            user = User(id=9001, first_name="Alice", is_bot=False, username="alice_biz")
            rights = BusinessBotRights(can_reply=True)
            bc = BusinessConnection(
                id="conn_abc",
                user=user,
                user_chat_id=9001,
                date=datetime.now(timezone.utc),
                is_enabled=True,
                rights=rights,
            )
            update = MagicMock(spec=Update)
            update.business_connection = bc

            context = self._context()
            await handle_business_connection(update, context)

            context.bot.send_message.assert_awaited_once()
            call_kwargs = context.bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == 9001
            assert "Telegram Business Connected" in call_kwargs["text"]
            assert "Granted" in call_kwargs["text"]

            # Connection saved in DB
            conn = await get_business_connection_for_user(9001)
            assert conn is not None
            assert conn.connection_id == "conn_abc"

    async def test_handle_business_connection_disabled(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            user = User(id=9002, first_name="Bob", is_bot=False)
            bc = BusinessConnection(
                id="conn_xyz",
                user=user,
                user_chat_id=9002,
                date=datetime.now(timezone.utc),
                is_enabled=False,
            )
            update = MagicMock(spec=Update)
            update.business_connection = bc

            context = self._context()
            await handle_business_connection(update, context)

            context.bot.send_message.assert_awaited_once()
            call_kwargs = context.bot.send_message.call_args.kwargs
            assert "Disconnected" in call_kwargs["text"]

    async def test_handle_business_message_sends_on_behalf(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            # Register connection and rule
            await register_business_connection("conn_msg_1", user_id=9003, user_chat_id=9003, can_reply=True, is_enabled=True)
            await add_business_rule(9003, "catalog", "Here is our product catalog: https://example.com")

            # Incoming message from a customer (id 555) in customer chat (id 555)
            customer = User(id=555, first_name="Customer", is_bot=False)
            chat = Chat(id=555, type="private")
            biz_msg = Message(
                message_id=101,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=customer,
                text="Could you send the catalog please?",
                business_connection_id="conn_msg_1",
            )
            update = MagicMock(spec=Update)
            update.business_message = biz_msg

            context = self._context()
            await handle_business_message(update, context)

            # Bot must send message into chat 555 with business_connection_id="conn_msg_1"
            context.bot.send_message.assert_awaited_once_with(
                chat_id=555,
                text="Here is our product catalog: https://example.com",
                business_connection_id="conn_msg_1",
            )

    async def test_handle_business_message_ignores_owner(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("conn_msg_2", user_id=9004, user_chat_id=9004, can_reply=True, is_enabled=True)
            await add_business_rule(9004, "price", "$100")

            # Message sent by owner (id 9004)
            owner = User(id=9004, first_name="Owner", is_bot=False)
            chat = Chat(id=555, type="private")
            biz_msg = Message(
                message_id=102,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=owner,
                text="What price did you see?",
                business_connection_id="conn_msg_2",
            )
            update = MagicMock(spec=Update)
            update.business_message = biz_msg

            context = self._context()
            await handle_business_message(update, context)

            # Must NOT reply to owner
            context.bot.send_message.assert_not_awaited()

    async def test_business_commands(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            user = User(id=9005, first_name="Charlie", is_bot=False)
            chat = Chat(id=9005, type="private")
            msg = MagicMock(spec=Message)
            msg.reply_html = AsyncMock()
            msg.reply_text = AsyncMock()
            update = MagicMock(spec=Update)
            update.effective_user = user
            update.effective_chat = chat
            update.effective_message = msg

            context = self._context()

            # 1. /business in private chat
            await business_command(update, context)
            msg.reply_html.assert_awaited()
            rendered = msg.reply_html.call_args.args[0]
            assert "Business" in rendered

            # 2. /bizadd
            context.args = ["discount", "Use code SAVE10 for 10% off!"]
            await bizadd_command(update, context)
            assert "discount" in msg.reply_html.call_args.args[0]

            # 3. /bizrules
            await bizrules_command(update, context)
            assert "discount" in msg.reply_html.call_args.args[0]

            # 4. /bizdel
            context.args = ["discount"]
            await bizdel_command(update, context)
            assert "removed" in msg.reply_html.call_args.args[0]

            # 5. /bizgreeting
            context.args = ["Hello and welcome!"]
            await bizgreeting_command(update, context)
            assert "Hello and welcome!" in msg.reply_html.call_args.args[0]

            # 6. /bizaway
            context.args = ["Away for lunch."]
            await bizaway_command(update, context)
            assert "Away for lunch." in msg.reply_html.call_args.args[0]

            # 7. /bizstatus when not connected
            await bizstatus_command(update, context)
            assert "No Telegram Business connection found" in msg.reply_html.call_args.args[0]

            # Connect user and test /bizstatus when connected
            await register_business_connection("c_9005", user_id=9005, user_chat_id=9005, can_reply=True, is_enabled=True)
            await bizstatus_command(update, context)
            assert "Diagnostic Status" in msg.reply_html.call_args.args[0]

    async def test_biz_callback_actions(self, db_session):
        with patch("app.services.business.get_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = db_session

            await register_business_connection("c_9006", user_id=9006, user_chat_id=9006, can_reply=True, is_enabled=True)

            user = User(id=9006, first_name="Dan", is_bot=False)
            query = MagicMock()
            query.answer = AsyncMock()
            query.edit_message_text = AsyncMock()
            query.message = MagicMock()
            query.message.delete = AsyncMock()

            update = MagicMock(spec=Update)
            update.effective_user = user
            update.callback_query = query
            context = self._context()

            # 1. Toggle auto-reply
            query.data = "biz:toggle_autoreply"
            await biz_callback(update, context)
            query.answer.assert_awaited()
            query.edit_message_text.assert_awaited()
            conn = await get_business_connection_for_user(9006)
            assert conn.auto_reply_enabled is False

            # 2. Toggle greeting
            query.data = "biz:toggle_greeting"
            await biz_callback(update, context)
            conn = await get_business_connection_for_user(9006)
            assert conn.greeting_enabled is True

            # 3. Toggle away
            query.data = "biz:toggle_away"
            await biz_callback(update, context)
            conn = await get_business_connection_for_user(9006)
            assert conn.away_enabled is True

            # 4. View rules
            query.data = "biz:rules"
            await biz_callback(update, context)
            assert "Active Business Keywords" in query.edit_message_text.call_args.args[0]

            # 5. Help
            query.data = "biz:help"
            await biz_callback(update, context)
            assert "Business Chat Automation Guide" in query.edit_message_text.call_args.args[0]

            # 6. Close
            query.data = "biz:close"
            await biz_callback(update, context)
            query.message.delete.assert_awaited()



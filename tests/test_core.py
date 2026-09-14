"""
Tests for Aegis — V0.1 core functionality.
"""
import asyncio
import pytest
from datetime import datetime, timezone

from app.database.base import utc_now
from app.database.connection import get_session, init_db, close_db, get_async_database_url
from app.database.models.group import Group
from app.database.models.member import Member
from app.database.models.settings import GroupSettings
from app.database.models.warning import Warning
from app.database.models.audit_log import AuditLog
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.warnings import WarningRepository
from app.database.repositories.settings import SettingsRepository
from app.database.repositories.audit_logs import AuditLogRepository
from app.bot.middleware.auth import role_rank, ROLE_HIERARCHY
from app.bot.middleware.throttling import check_rate_limit


class TestTimestampMixin:
    def test_utc_now_returns_utc_datetime(self):
        now = utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc


class TestDatabaseConnection:
    def test_get_async_database_url_postgres_conversion(self):
        url = "postgres://user:pass@localhost/db"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@localhost/db"
    
    def test_get_async_database_url_sqlite_conversion(self):
        url = "sqlite:///./test.db"
        result = get_async_database_url(url)
        assert result == "sqlite+aiosqlite:///./test.db"


class TestGroupModel:
    def test_group_creation(self):
        group = Group(telegram_id=123456789, title="Test Group", type="supergroup", username="testgroup")
        assert group.telegram_id == 123456789
        assert group.title == "Test Group"
    
    def test_group_repr(self):
        group = Group(id=1, telegram_id=123456789, title="Test Group", type="supergroup")
        repr_str = repr(group)
        assert "Group" in repr_str
        assert "123456789" in repr_str


class TestMemberModel:
    def test_member_creation(self):
        member = Member(group_id=1, telegram_id=987654321, username="testuser", role="member")
        assert member.group_id == 1
        assert member.role == "member"

    def test_member_role_client_default(self):
        # SQLAlchemy client-side `default` is applied on flush, not __init__.
        col = Member.__table__.c.role
        assert col.default.arg == "member"
        assert col.server_default.arg == "member"


class TestGroupSettingsModel:
    def test_settings_defaults_applied_on_flush(self):
        # Column defaults are applied at INSERT time; verify config instead.
        assert GroupSettings.__table__.c.warn_limit.default.arg == 3
        assert GroupSettings.__table__.c.welcome_enabled.default.arg is False

    def test_welcome_goodbye_message_columns_are_nullable_text(self):
        from sqlalchemy import Text
        assert GroupSettings.__table__.c.welcome_message.type is not None
        assert GroupSettings.__table__.c.welcome_message.nullable is True
        assert GroupSettings.__table__.c.goodbye_message.nullable is True
        assert GroupSettings.__table__.c.welcome_message.type.__class__ is Text
        assert GroupSettings.__table__.c.goodbye_message.type.__class__ is Text


class TestWarningModel:
    def test_warning_creation(self):
        warning = Warning(group_id=1, user_id=987654321, issued_by=123456789, reason="Spamming")
        assert warning.group_id == 1
        assert warning.reason == "Spamming"


class TestAuditLogModel:
    def test_audit_log_creation(self):
        log = AuditLog(group_id=1, actor_id=123456789, action="TEST_ACTION")
        assert log.action == "TEST_ACTION"


class TestGroupRepository:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    @pytest.mark.asyncio
    async def test_upsert_group_creates_new(self):
        await init_db()
        async with get_session() as session:
            repo = GroupRepository(session)
            group = await repo.upsert_group(telegram_id=123456789, title="Test Group", type_="supergroup")
            assert group.id is not None
            assert group.telegram_id == 123456789

    @pytest.mark.asyncio
    async def test_upsert_group_updates_existing(self):
        await init_db()
        async with get_session() as session:
            repo = GroupRepository(session)
            group = await repo.upsert_group(telegram_id=123456789, title="Original", type_="supergroup")
            original_id = group.id
            updated = await repo.upsert_group(telegram_id=123456789, title="Updated", type_="supergroup")
            assert updated.id == original_id
            assert updated.title == "Updated"


class TestMemberRepository:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    @pytest.mark.asyncio
    async def test_upsert_member_creates_new(self):
        await init_db()
        async with get_session() as session:
            group_repo = GroupRepository(session)
            member_repo = MemberRepository(session)
            group = await group_repo.upsert_group(telegram_id=123456789, title="TG", type_="supergroup")
            await session.commit()
            member = await member_repo.upsert_member(group_id=group.id, telegram_id=987654321, role="member")
            assert member.id is not None
            assert member.group_id == group.id

    @pytest.mark.asyncio
    async def test_list_admins(self):
        await init_db()
        async with get_session() as session:
            group_repo = GroupRepository(session)
            member_repo = MemberRepository(session)
            group = await group_repo.upsert_group(telegram_id=123456789, title="TG", type_="supergroup")
            await session.commit()
            await member_repo.upsert_member(group_id=group.id, telegram_id=1, role="owner")
            await member_repo.upsert_member(group_id=group.id, telegram_id=2, role="admin")
            await session.commit()
        async with get_session() as session:
            member_repo = MemberRepository(session)
            admins = await member_repo.list_admins(group.id)
            assert len(admins) == 2


class TestWarningRepository:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    @pytest.mark.asyncio
    async def test_add_warning(self):
        await init_db()
        async with get_session() as session:
            group_repo = GroupRepository(session)
            warning_repo = WarningRepository(session)
            group = await group_repo.upsert_group(telegram_id=123456789, title="TG", type_="supergroup")
            await session.commit()
            w = await warning_repo.add_warning(group_id=group.id, user_id=987654321, issued_by=111, reason="T")
            assert w.id is not None
            assert w.group_id == group.id

    @pytest.mark.asyncio
    async def test_count_and_reset(self):
        await init_db()
        async with get_session() as session:
            group_repo = GroupRepository(session)
            warning_repo = WarningRepository(session)
            group = await group_repo.upsert_group(telegram_id=123456789, title="TG", type_="supergroup")
            await session.commit()
            await warning_repo.add_warning(group_id=group.id, user_id=9, issued_by=1, reason="W1")
            await warning_repo.add_warning(group_id=group.id, user_id=9, issued_by=1, reason="W2")
            await session.commit()
        async with get_session() as session:
            warning_repo = WarningRepository(session)
            count = await warning_repo.count_warnings_for_user(group.id, 9)
            assert count == 2
            cleared = await warning_repo.reset_warnings(group.id, 9)
            assert cleared == 2
            count2 = await warning_repo.count_warnings_for_user(group.id, 9)
            assert count2 == 0


class TestSettingsRepository:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    @pytest.mark.asyncio
    async def test_get_or_create(self):
        await init_db()
        async with get_session() as session:
            group_repo = GroupRepository(session)
            settings_repo = SettingsRepository(session)
            group = await group_repo.upsert_group(telegram_id=123456789, title="TG", type_="supergroup")
            await session.commit()
            s = await settings_repo.get_or_create(group.id)
            assert s.group_id == group.id
            assert s.warn_limit == 3

    @pytest.mark.asyncio
    async def test_update_settings(self):
        await init_db()
        async with get_session() as session:
            group_repo = GroupRepository(session)
            settings_repo = SettingsRepository(session)
            group = await group_repo.upsert_group(telegram_id=123456789, title="TG", type_="supergroup")
            await session.commit()
            s = await settings_repo.update(group.id, warn_limit=5, welcome_enabled=True)
            assert s.warn_limit == 5
            assert s.welcome_enabled is True


class TestAuditLogRepository:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        asyncio.run(close_db())

    @pytest.mark.asyncio
    async def test_log_event(self):
        await init_db()
        async with get_session() as session:
            audit_repo = AuditLogRepository(session)
            log = await audit_repo.log_event(action="TEST", group_id=1, actor_id=111, target_id=222)
            assert log.id is not None
            assert log.action == "TEST"

    @pytest.mark.asyncio
    async def test_get_recent_logs(self):
        await init_db()
        async with get_session() as session:
            audit_repo = AuditLogRepository(session)
            for i in range(5):
                await audit_repo.log_event(action=f"A_{i}", group_id=1, actor_id=111)
            await session.commit()
        async with get_session() as session:
            audit_repo = AuditLogRepository(session)
            logs = await audit_repo.get_recent_logs(group_id=1, limit=3)
            assert len(logs) == 3


class TestConfigSettings:
    def test_parse_super_admin_ids_from_string(self):
        from app.config.settings import Settings
        result = Settings.parse_super_admins("123,456,789")
        assert result == [123, 456, 789]

    def test_parse_super_admin_ids_empty_string(self):
        from app.config.settings import Settings
        result = Settings.parse_super_admins("")
        assert result == []

    def test_parse_super_admin_ids_none(self):
        from app.config.settings import Settings
        result = Settings.parse_super_admins(None)
        assert result == []


class TestMiddlewareAuth:
    def test_role_rank(self):
        assert role_rank("member") == 0
        assert role_rank("moderator") == 1
        assert role_rank("admin") == 2
        assert role_rank("owner") == 3
        assert role_rank("unknown") == 0

    def test_role_hierarchy_order(self):
        assert ROLE_HIERARCHY == ["member", "moderator", "admin", "owner"]


class TestMiddlewareThrottling:
    def setup_method(self):
        import app.bot.middleware.throttling as throttling
        throttling._rate_store.clear()

    def test_rate_limit_allowed_first_call(self):
        assert check_rate_limit(user_id=1, command="test", max_calls=5, window_seconds=30.0)

    def test_rate_limit_blocks_after_max(self):
        for _ in range(5):
            assert check_rate_limit(user_id=1, command="test", max_calls=5, window_seconds=30.0)
        assert not check_rate_limit(user_id=1, command="test", max_calls=5, window_seconds=30.0)
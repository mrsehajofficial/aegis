import logging
from typing import Optional
from telegram import Bot, Chat, ChatMemberAdministrator, ChatMemberOwner

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.settings import SettingsRepository
from app.database.repositories.audit_logs import AuditLogRepository

logger = logging.getLogger(__name__)


async def register_or_update_group(chat: Chat) -> int:
    """
    Upsert a group into the database and ensure its default settings exist.
    Returns the internal DB group_id.
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        settings_repo = SettingsRepository(session)

        group = await group_repo.upsert_group(
            telegram_id=chat.id,
            title=chat.title or "Unknown Group",
            type_=chat.type,
            username=chat.username,
        )
        settings = await settings_repo.get_or_create(group.id)
        # Enable welcome and goodbye messages by default for new groups
        if not settings.welcome_enabled or not settings.goodbye_enabled:
            await settings_repo.update(
                group.id,
                welcome_enabled=True,
                goodbye_enabled=True,
            )
            logger.info(
                f"Enabled welcome/goodbye messages for new group {chat.title!r} (id={chat.id})"
            )
        await session.commit()

        logger.info(f"Group registered/updated: {chat.title!r} (telegram_id={chat.id}, db_id={group.id})")
        return group.id


async def sync_group_admins(chat: Chat, bot: Bot) -> None:
    """
    Fetches the current admin list from Telegram and upserts them as 'owner' or 'admin' in the DB.
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)

        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            logger.warning(f"sync_group_admins called for unregistered group {chat.id}")
            return

        try:
            admins = await bot.get_chat_administrators(chat.id)
        except Exception as e:
            logger.error(f"Failed to fetch admins for group {chat.id}: {e}")
            return

        for admin in admins:
            user = admin.user
            if user.is_bot:
                continue  # Skip other bots

            if isinstance(admin, ChatMemberOwner):
                role = "owner"
            elif isinstance(admin, ChatMemberAdministrator):
                role = "admin"
            else:
                role = "admin"

            await member_repo.upsert_member(
                group_id=group.id,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                role=role,
            )

        await session.commit()
        logger.info(f"Synced {len(admins)} admins for group {chat.title!r} (db_id={group.id})")


async def log_bot_added(chat: Chat, actor_id: Optional[int] = None) -> None:
    """Log a BOT_ADDED audit event."""
    async with get_session() as session:
        group_repo = GroupRepository(session)
        audit_repo = AuditLogRepository(session)

        group = await group_repo.get_by_telegram_id(chat.id)
        if group:
            await audit_repo.log_event(
                action="BOT_ADDED",
                group_id=group.id,
                actor_id=actor_id,
                metadata={"chat_title": chat.title, "chat_type": chat.type},
            )
            await session.commit()

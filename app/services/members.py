import logging
from typing import Optional
from telegram import User, Chat

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository

logger = logging.getLogger(__name__)


async def get_or_create_member(
    chat: Chat,
    user: User,
    role: str = "member"
) -> Optional[int]:
    """
    Ensures a member record exists for a user in a group.
    Returns the internal member DB id, or None if the group is not registered.
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)

        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            logger.warning(f"get_or_create_member: group {chat.id} not registered")
            return None

        member = await member_repo.upsert_member(
            group_id=group.id,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role=role,
        )
        await session.commit()
        return member.id


async def get_member_role(chat: Chat, user: User) -> str:
    """
    Returns the stored role of a user in the given group ('owner', 'admin', 'member').
    Defaults to 'member' if not found.
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)

        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            return "member"

        member = await member_repo.get_member(group.id, user.id)
        return member.role if member else "member"

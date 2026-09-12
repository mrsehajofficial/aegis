"""
Ban service — Manages user bans within groups.

Provides functionality to ban, unban, and check ban status for members.
Designed for V0.2 implementation with full audit logging.
"""
import logging
from typing import Optional
from telegram import User, Chat

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.audit_logs import AuditLogRepository

logger = logging.getLogger(__name__)


async def ban_user(
    chat: Chat,
    admin: User,
    target: User,
    reason: Optional[str] = None,
    revoke_permissions: bool = True,
) -> bool:
    """
    Ban a user from a group.
    
    Args:
        chat: The group chat
        admin: The admin performing the ban
        target: The user to ban
        reason: Optional reason for the ban
        revoke_permissions: Whether to revoke chat permissions
        
    Returns:
        True if the ban was successful
        
    Raises:
        ValueError: If the group is not registered or admin is not authorized
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)
        audit_repo = AuditLogRepository(session)
        
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            raise ValueError(f"Group {chat.id} is not registered")
        
        # Verify admin is owner or admin
        admin_member = await member_repo.get_member(group.id, admin.id)
        if admin_member is None or admin_member.role not in ("owner", "admin"):
            raise ValueError("Only admins can ban users")
        
        # Log the ban action
        await audit_repo.log_event(
            action="USER_BANNED",
            group_id=group.id,
            actor_id=admin.id,
            target_id=target.id,
            reason=reason,
            metadata={"revoke_permissions": revoke_permissions},
        )
        await session.commit()
        
        logger.info(
            f"User banned: user={target.id} in group={group.id} "
            f"by {admin.id} reason={reason!r}"
        )
        
        return True


async def unban_user(
    chat: Chat,
    admin: User,
    target: User,
) -> bool:
    """
    Unban a user from a group.
    
    Args:
        chat: The group chat
        admin: The admin performing the unban
        target: The user to unban
        
    Returns:
        True if the unban was successful
        
    Raises:
        ValueError: If the group is not registered or admin is not authorized
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)
        audit_repo = AuditLogRepository(session)
        
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            raise ValueError(f"Group {chat.id} is not registered")
        
        # Verify admin is owner or admin
        admin_member = await member_repo.get_member(group.id, admin.id)
        if admin_member is None or admin_member.role not in ("owner", "admin"):
            raise ValueError("Only admins can unban users")
        
        # Log the unban action
        await audit_repo.log_event(
            action="USER_UNBANNED",
            group_id=group.id,
            actor_id=admin.id,
            target_id=target.id,
            metadata={},
        )
        await session.commit()
        
        logger.info(
            f"User unbanned: user={target.id} in group={group.id} "
            f"by {admin.id}"
        )
        
        return True


async def is_user_banned(chat: Chat, target: User) -> bool:
    """
    Check if a user is banned from a group.
    
    Args:
        chat: The group chat
        target: The user to check
        
    Returns:
        True if the user is banned, False otherwise
    """
    try:
        chat_member = await chat.get_member(target.id)
        return chat_member.status == "kicked"
    except Exception:
        return False


async def kick_user(
    chat: Chat,
    admin: User,
    target: User,
    reason: Optional[str] = None,
) -> bool:
    """
    Kick a user from a group without banning them.
    
    Args:
        chat: The group chat
        admin: The admin performing the kick
        target: The user to kick
        reason: Optional reason for the kick
        
    Returns:
        True if the kick was successful
        
    Raises:
        ValueError: If the group is not registered or admin is not authorized
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)
        audit_repo = AuditLogRepository(session)
        
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            raise ValueError(f"Group {chat.id} is not registered")
        
        # Verify admin is owner or admin
        admin_member = await member_repo.get_member(group.id, admin.id)
        if admin_member is None or admin_member.role not in ("owner", "admin"):
            raise ValueError("Only admins can kick users")
        
        # Log the kick action
        await audit_repo.log_event(
            action="USER_KICKED",
            group_id=group.id,
            actor_id=admin.id,
            target_id=target.id,
            reason=reason,
            metadata={},
        )
        await session.commit()
        
        logger.info(
            f"User kicked: user={target.id} in group={group.id} "
            f"by {admin.id} reason={reason!r}"
        )
        
        return True

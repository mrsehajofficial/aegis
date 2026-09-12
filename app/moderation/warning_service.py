"""
Warning service — Manages user warnings within groups.

Provides functionality to issue, view, and reset warnings for members.
Designed for V0.3 implementation with full audit logging.
"""
import logging
from typing import Optional, List
from telegram import User, Chat

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.members import MemberRepository
from app.database.repositories.warnings import WarningRepository
from app.database.repositories.audit_logs import AuditLogRepository

logger = logging.getLogger(__name__)


async def issue_warning(
    chat: Chat,
    issuer: User,
    target: User,
    reason: Optional[str] = None,
) -> int:
    """
    Issue a warning to a user in a group.
    
    Args:
        chat: The group chat where the warning is issued
        issuer: The admin who is issuing the warning
        target: The user receiving the warning
        reason: Optional reason for the warning
        
    Returns:
        The total warning count for the user after this warning
        
    Raises:
        ValueError: If the group is not registered or issuer is not an admin
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)
        warning_repo = WarningRepository(session)
        audit_repo = AuditLogRepository(session)
        
        # Get or create the group
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            raise ValueError(f"Group {chat.id} is not registered")
        
        # Verify issuer is admin or owner
        issuer_member = await member_repo.get_member(group.id, issuer.id)
        if issuer_member is None or issuer_member.role not in ("owner", "admin"):
            raise ValueError("Only admins can issue warnings")
        
        # Record the warning
        warning = await warning_repo.add_warning(
            group_id=group.id,
            user_id=target.id,
            issued_by=issuer.id,
            reason=reason,
        )
        await session.commit()
        
        # Log the action
        await audit_repo.log_event(
            action="WARNING_ISSUED",
            group_id=group.id,
            actor_id=issuer.id,
            target_id=target.id,
            reason=reason,
            metadata={
                "warning_id": warning.id,
                "total_warnings": await warning_repo.count_warnings_for_user(group.id, target.id)
            },
        )
        await session.commit()
        
        logger.info(
            f"Warning issued: user={target.id} in group={group.id} "
            f"by {issuer.id} reason={reason!r}"
        )
        
        return await warning_repo.count_warnings_for_user(group.id, target.id)


async def get_user_warnings(
    chat: Chat,
    target: User,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    """
    Retrieve all warnings for a user in a group.
    
    Args:
        chat: The group chat
        target: The user to get warnings for
        limit: Maximum number of warnings to return
        offset: Pagination offset
        
    Returns:
        List of warning dictionaries with id, issued_by, reason, created_at
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        warning_repo = WarningRepository(session)
        
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            return []
        
        warnings = await warning_repo.get_warnings_for_user(
            group.id, target.id, limit=limit, offset=offset
        )
        
        return [
            {
                "id": w.id,
                "issued_by": w.issued_by,
                "reason": w.reason,
                "created_at": w.created_at.isoformat(),
            }
            for w in warnings
        ]


async def reset_user_warnings(chat: Chat, target: User, actor: User) -> int:
    """
    Reset (clear) all warnings for a user in a group.
    
    Args:
        chat: The group chat
        target: The user whose warnings will be cleared
        actor: The admin performing the reset
        
    Returns:
        Number of warnings that were cleared
        
    Raises:
        ValueError: If the group is not registered or actor is not an admin
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        member_repo = MemberRepository(session)
        warning_repo = WarningRepository(session)
        audit_repo = AuditLogRepository(session)
        
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            raise ValueError(f"Group {chat.id} is not registered")
        
        # Verify actor is admin or owner
        actor_member = await member_repo.get_member(group.id, actor.id)
        if actor_member is None or actor_member.role not in ("owner", "admin"):
            raise ValueError("Only admins can reset warnings")
        
        count = await warning_repo.reset_warnings(group.id, target.id)
        
        # Log the action
        await audit_repo.log_event(
            action="WARNINGS_RESET",
            group_id=group.id,
            actor_id=actor.id,
            target_id=target.id,
            metadata={"warnings_cleared": count},
        )
        await session.commit()
        
        logger.info(
            f"Warnings reset: user={target.id} in group={group.id} "
            f"by {actor.id} cleared={count}"
        )
        
        return count


async def get_warning_count(chat: Chat, target: User) -> int:
    """
    Get the total number of warnings for a user in a group.
    
    Args:
        chat: The group chat
        target: The user to count warnings for
        
    Returns:
        Number of warnings
    """
    async with get_session() as session:
        group_repo = GroupRepository(session)
        warning_repo = WarningRepository(session)
        
        group = await group_repo.get_by_telegram_id(chat.id)
        if group is None:
            return 0
        
        return await warning_repo.count_warnings_for_user(group.id, target.id)

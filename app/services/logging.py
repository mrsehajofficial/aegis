import logging
from typing import Optional, Any, Dict

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.audit_logs import AuditLogRepository

logger = logging.getLogger(__name__)


async def log_action(
    action: str,
    group_telegram_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    target_id: Optional[int] = None,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record an audit log entry. Resolves group telegram_id → internal group_id automatically.
    """
    async with get_session() as session:
        audit_repo = AuditLogRepository(session)
        group_id: Optional[int] = None

        if group_telegram_id is not None:
            group_repo = GroupRepository(session)
            group = await group_repo.get_by_telegram_id(group_telegram_id)
            if group:
                group_id = group.id

        await audit_repo.log_event(
            action=action,
            group_id=group_id,
            actor_id=actor_id,
            target_id=target_id,
            reason=reason,
            metadata=metadata,
        )
        await session.commit()
        logger.debug(
            f"[AUDIT] action={action} group={group_telegram_id} "
            f"actor={actor_id} target={target_id} reason={reason!r}"
        )

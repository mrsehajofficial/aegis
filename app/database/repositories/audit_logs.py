from typing import Optional, Dict, Any, Sequence
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.audit_log import AuditLog
from app.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)

    async def log_event(
        self,
        action: str,
        group_id: Optional[int] = None,
        actor_id: Optional[int] = None,
        target_id: Optional[int] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        log = AuditLog(
            action=action,
            group_id=group_id,
            actor_id=actor_id,
            target_id=target_id,
            reason=reason,
            metadata_=metadata
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def count_for_group(self, group_id: int) -> int:
        """Total audit entries recorded for a group."""
        query = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.group_id == group_id)
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def action_counts(self, group_id: int, limit: int = 8) -> list[tuple[str, int]]:
        """Top moderation actions by volume, e.g. [("BANNED", 12), ("MUTED", 7)]."""
        query = (
            select(AuditLog.action, func.count().label("n"))
            .where(AuditLog.group_id == group_id)
            .group_by(AuditLog.action)
            .order_by(desc("n"))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def get_recent_logs(
        self,
        group_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> Sequence[AuditLog]:
        query = (
            select(AuditLog)
            .where(AuditLog.group_id == group_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

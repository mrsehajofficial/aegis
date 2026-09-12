from typing import Optional, Dict, Any, Sequence
from sqlalchemy import select, desc
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

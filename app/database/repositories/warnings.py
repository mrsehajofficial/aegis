"""
Warning repository — CRUD operations for member warnings.

Used by the moderation system to track, query, and manage warnings
for users across groups. Implemented for V0.3.
"""
from datetime import datetime
from typing import Optional, Sequence
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.warning import Warning
from app.database.repositories.base import BaseRepository
from app.database.base import utc_now


class WarningRepository(BaseRepository[Warning]):
    def __init__(self, session: AsyncSession):
        super().__init__(Warning, session)

    async def get_by_id(self, warning_id: int) -> Optional[Warning]:
        return await self.session.get(self.model, warning_id)

    async def get_warnings_for_user(
        self, group_id: int, user_id: int, limit: int = 50, offset: int = 0
    ) -> Sequence[Warning]:
        query = (
            select(Warning)
            .where(Warning.group_id == group_id, Warning.user_id == user_id)
            .order_by(desc(Warning.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_warnings_for_user(self, group_id: int, user_id: int) -> int:
        from sqlalchemy import func
        query = select(func.count()).select_from(
            Warning.__table__
        ).where(
            Warning.group_id == group_id,
            Warning.user_id == user_id
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def add_warning(
        self,
        group_id: int,
        user_id: int,
        issued_by: int,
        reason: Optional[str] = None,
    ) -> Warning:
        warning = Warning(
            group_id=group_id,
            user_id=user_id,
            issued_by=issued_by,
            reason=reason,
            created_at=utc_now(),
        )
        self.session.add(warning)
        await self.session.flush()
        return warning

    async def delete_warning(self, warning_id: int) -> bool:
        warning = await self.get_by_id(warning_id)
        if warning:
            await self.session.delete(warning)
            await self.session.flush()
            return True
        return False

    async def reset_warnings(self, group_id: int, user_id: int) -> int:
        """Delete all warnings for a user in a group. Returns count of deleted warnings."""
        from sqlalchemy import delete
        result = await self.session.execute(
            delete(Warning).where(
                Warning.group_id == group_id,
                Warning.user_id == user_id
            )
        )
        await self.session.flush()
        return result.rowcount

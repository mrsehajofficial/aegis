"""
Repository for managing auto-reply filters.
"""
from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.filter import Filter
from app.database.repositories.base import BaseRepository


class FilterRepository(BaseRepository[Filter]):
    def __init__(self, session: AsyncSession):
        super().__init__(Filter, session)

    async def get_by_group(self, group_id: int) -> Sequence[Filter]:
        query = select(Filter).where(Filter.group_id == group_id).order_by(Filter.trigger)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_id(self, filter_id: int) -> Optional[Filter]:
        query = select(Filter).where(Filter.id == filter_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_group_and_trigger(self, group_id: int, trigger: str) -> Optional[Filter]:
        query = select(Filter).where(
            Filter.group_id == group_id,
            Filter.trigger == trigger.lower().strip()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        group_id: int,
        trigger: str,
        response: str,
        enabled: bool = True,
    ) -> Filter:
        """Create or update a filter for the given trigger (upsert by trigger)."""
        existing = await self.get_by_group_and_trigger(group_id, trigger)
        if existing:
            existing.response = response
            existing.enabled = enabled
            await self.session.flush()
            return existing
        f = Filter(
            group_id=group_id,
            trigger=trigger.lower().strip(),
            response=response,
            enabled=enabled,
        )
        self.session.add(f)
        await self.session.flush()
        return f

    async def delete_by_id(self, filter_id: int) -> Optional[Filter]:
        f = await self.get_by_id(filter_id)
        if f:
            await self.session.delete(f)
            await self.session.flush()
        return f

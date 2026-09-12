from typing import Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.settings import GroupSettings
from app.database.repositories.base import BaseRepository


class SettingsRepository(BaseRepository[GroupSettings]):
    def __init__(self, session: AsyncSession):
        super().__init__(GroupSettings, session)

    async def get_by_group_id(self, group_id: int) -> Optional[GroupSettings]:
        query = select(GroupSettings).where(GroupSettings.group_id == group_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(self, group_id: int) -> GroupSettings:
        settings = await self.get_by_group_id(group_id)
        if settings is None:
            settings = GroupSettings(group_id=group_id)
            self.session.add(settings)
            await self.session.flush()
        return settings

    async def update(self, group_id: int, **kwargs: Any) -> GroupSettings:
        settings = await self.get_or_create(group_id)
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        await self.session.flush()
        return settings

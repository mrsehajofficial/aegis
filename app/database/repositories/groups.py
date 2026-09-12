from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.group import Group
from app.database.repositories.base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    def __init__(self, session: AsyncSession):
        super().__init__(Group, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Group]:
        query = select(Group).where(Group.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def upsert_group(
        self,
        telegram_id: int,
        title: str,
        type_: str,
        username: Optional[str] = None
    ) -> Group:
        group = await self.get_by_telegram_id(telegram_id)
        if group is None:
            group = Group(
                telegram_id=telegram_id,
                title=title,
                type=type_,
                username=username
            )
            self.session.add(group)
        else:
            group.title = title
            group.type = type_
            group.username = username

        await self.session.flush()
        return group

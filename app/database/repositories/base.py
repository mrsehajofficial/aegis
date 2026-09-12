from typing import Generic, TypeVar, Type, Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        return await self.session.get(self.model, id)

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        query = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def add(self, entity: ModelType) -> ModelType:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelType) -> None:
        await self.session.delete(entity)
        await self.session.flush()

from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.protection import Blacklist, Note
from app.database.repositories.base import BaseRepository


class BlacklistRepository(BaseRepository[Blacklist]):
    def __init__(self, session: AsyncSession):
        super().__init__(Blacklist, session)

    async def get_by_group(self, group_id: int) -> Sequence[Blacklist]:
        query = select(Blacklist).where(Blacklist.group_id == group_id).order_by(Blacklist.word)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_word(self, group_id: int, word: str) -> Optional[Blacklist]:
        query = select(Blacklist).where(
            Blacklist.group_id == group_id,
            Blacklist.word == word.lower().strip()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add_word(self, group_id: int, word: str, action: str = "delete") -> Blacklist:
        existing = await self.get_word(group_id, word)
        if existing:
            existing.action = action
            await self.session.flush()
            return existing
        bl = Blacklist(group_id=group_id, word=word.lower().strip(), action=action)
        self.session.add(bl)
        await self.session.flush()
        return bl

    async def remove_word(self, group_id: int, word: str) -> bool:
        bl = await self.get_word(group_id, word)
        if bl:
            await self.session.delete(bl)
            await self.session.flush()
            return True
        return False

    async def clear_group(self, group_id: int) -> int:
        from sqlalchemy import delete
        result = await self.session.execute(
            delete(Blacklist).where(Blacklist.group_id == group_id)
        )
        await self.session.flush()
        return result.rowcount


class NoteRepository(BaseRepository[Note]):
    def __init__(self, session: AsyncSession):
        super().__init__(Note, session)

    async def get_by_group(self, group_id: int) -> Sequence[Note]:
        query = select(Note).where(Note.group_id == group_id).order_by(Note.keyword)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_note(self, group_id: int, keyword: str) -> Optional[Note]:
        query = select(Note).where(
            Note.group_id == group_id,
            Note.keyword == keyword.lower().strip()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def save_note(self, group_id: int, keyword: str, content: str) -> Note:
        from app.database.models.protection import Note
        existing = await self.get_note(group_id, keyword)
        if existing:
            existing.content = content
            await self.session.flush()
            return existing
        note = Note(group_id=group_id, keyword=keyword.lower().strip(), content=content)
        self.session.add(note)
        await self.session.flush()
        return note

    async def remove_note(self, group_id: int, keyword: str) -> bool:
        from app.database.models.protection import Note
        note = await self.get_note(group_id, keyword)
        if note:
            await self.session.delete(note)
            await self.session.flush()
            return True
        return False

    async def clear_group(self, group_id: int) -> int:
        from sqlalchemy import delete
        from app.database.models.protection import Note
        result = await self.session.execute(
            delete(Note).where(Note.group_id == group_id)
        )
        await self.session.flush()
        return result.rowcount
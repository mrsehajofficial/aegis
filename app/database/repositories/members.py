from datetime import datetime
from typing import Optional, Sequence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.member import Member
from app.database.repositories.base import BaseRepository
from app.database.base import utc_now


class MemberRepository(BaseRepository[Member]):
    def __init__(self, session: AsyncSession):
        super().__init__(Member, session)

    async def count_members(self, group_id: int) -> int:
        """Number of members tracked for a group (the username cache)."""
        query = (
            select(func.count())
            .select_from(Member)
            .where(Member.group_id == group_id)
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_role(self, group_id: int, role: str) -> int:
        """Number of members holding a given role in a group."""
        query = (
            select(func.count())
            .select_from(Member)
            .where(Member.group_id == group_id, Member.role == role)
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_member(self, group_id: int, telegram_id: int) -> Optional[Member]:
        query = select(Member).where(
            Member.group_id == group_id,
            Member.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_member_by_username(self, group_id: int, username: str) -> Optional[Member]:
        """Case-insensitive username lookup within a group (username cache)."""
        uname = (username or "").lstrip("@").lower()
        if not uname:
            return None
        query = select(Member).where(
            Member.group_id == group_id,
            func.lower(Member.username) == uname,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def upsert_member(
        self,
        group_id: int,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: str = "member",
        joined_at: Optional[datetime] = None,
        force_role: bool = False,
    ) -> Member:
        """Create or update a member record.

        By default (``force_role=False``) the stored role is *never downgraded*:
        if a member is already recorded as an admin/owner, tracking a new message
        from them won't silently demote them back to "member".
        Pass ``force_role=True`` (used by the admin-sync path) to override.
        """
        member = await self.get_member(group_id, telegram_id)
        if member is None:
            member = Member(
                group_id=group_id,
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=role,
                joined_at=joined_at or utc_now()
            )
            self.session.add(member)
        else:
            if username is not None:
                member.username = username
            if first_name is not None:
                member.first_name = first_name
            if last_name is not None:
                member.last_name = last_name
            # Only update the role if explicitly forced, or if the new role
            # is a promotion (higher privilege than what is already stored).
            _RANK = {"member": 0, "moderator": 1, "admin": 2, "owner": 3, "creator": 3}
            stored_rank = _RANK.get(member.role, 0)
            new_rank = _RANK.get(role, 0)
            if force_role or new_rank > stored_rank:
                member.role = role

        await self.session.flush()
        return member

    async def count_admins(self, group_id: int) -> int:
        """Count members with admin or owner/creator roles."""
        query = (
            select(func.count())
            .select_from(Member)
            .where(
                Member.group_id == group_id,
                Member.role.in_(["owner", "creator", "admin", "administrator"])
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def list_admins(self, group_id: int) -> Sequence[Member]:
        query = select(Member).where(
            Member.group_id == group_id,
            Member.role.in_(["owner", "creator", "admin", "administrator"])
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_admins(self, group_id: int) -> Sequence[Member]:
        """Alias for list_admins."""
        return await self.list_admins(group_id)

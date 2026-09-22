from typing import Optional, Sequence
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utc_now
from app.database.models.business import BusinessConnection, BusinessRule
from app.database.repositories.base import BaseRepository


class BusinessRepository(BaseRepository[BusinessConnection]):
    def __init__(self, session: AsyncSession):
        super().__init__(BusinessConnection, session)

    async def get_connection_by_id(self, connection_id: str) -> Optional[BusinessConnection]:
        stmt = select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_connection_by_user_id(self, user_id: int) -> Optional[BusinessConnection]:
        stmt = (
            select(BusinessConnection)
            .where(BusinessConnection.user_id == user_id)
            .order_by(BusinessConnection.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert_connection(
        self,
        connection_id: str,
        user_id: int,
        user_chat_id: Optional[int],
        can_reply: bool,
        is_enabled: bool,
    ) -> BusinessConnection:
        conn = await self.get_connection_by_id(connection_id)
        now = utc_now()
        if conn is None:
            conn = BusinessConnection(
                connection_id=connection_id,
                user_id=user_id,
                user_chat_id=user_chat_id,
                can_reply=can_reply,
                is_enabled=is_enabled,
                auto_reply_enabled=True,
                greeting_enabled=False,
                away_enabled=False,
                connected_at=now,
                updated_at=now,
            )
            self.session.add(conn)
        else:
            conn.user_id = user_id
            if user_chat_id is not None:
                conn.user_chat_id = user_chat_id
            conn.can_reply = can_reply
            conn.is_enabled = is_enabled
            conn.updated_at = now
        await self.session.flush()
        return conn

    async def get_rules(self, user_id: int, enabled_only: bool = False) -> Sequence[BusinessRule]:
        stmt = select(BusinessRule).where(BusinessRule.user_id == user_id)
        if enabled_only:
            stmt = stmt.where(BusinessRule.enabled == True)  # noqa: E712
        stmt = stmt.order_by(BusinessRule.trigger.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_rule_by_trigger(self, user_id: int, trigger: str) -> Optional[BusinessRule]:
        normalized = trigger.strip().lower()
        stmt = select(BusinessRule).where(
            BusinessRule.user_id == user_id,
            BusinessRule.trigger == normalized,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_or_update_rule(
        self,
        user_id: int,
        trigger: str,
        response: str,
        match_type: str = "contains",
        connection_id: Optional[str] = None,
    ) -> BusinessRule:
        normalized = trigger.strip().lower()
        rule = await self.get_rule_by_trigger(user_id, normalized)
        now = utc_now()
        if rule is None:
            rule = BusinessRule(
                user_id=user_id,
                connection_id=connection_id,
                trigger=normalized,
                response=response,
                match_type=match_type,
                enabled=True,
                created_at=now,
            )
            self.session.add(rule)
        else:
            rule.response = response
            rule.match_type = match_type
            rule.enabled = True
            if connection_id:
                rule.connection_id = connection_id
        await self.session.flush()
        return rule

    async def delete_rule(self, user_id: int, trigger: str) -> bool:
        normalized = trigger.strip().lower()
        rule = await self.get_rule_by_trigger(user_id, normalized)
        if rule is not None:
            await self.session.delete(rule)
            await self.session.flush()
            return True
        return False

from typing import Optional

from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.database.models.settings import GroupSettings


async def get_group_settings(group_telegram_id: int) -> Optional[GroupSettings]:
    """Retrieve settings for a group by its Telegram ID."""
    async with get_session() as session:
        group_repo = GroupRepository(session)
        settings_repo = SettingsRepository(session)

        group = await group_repo.get_by_telegram_id(group_telegram_id)
        if group is None:
            return None

        return await settings_repo.get_or_create(group.id)

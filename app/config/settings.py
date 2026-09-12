from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    BOT_TOKEN: str = "dummy_token"
    DATABASE_URL: str = "sqlite+aiosqlite:///./aegis.db"
    LOG_LEVEL: str = "INFO"
    SUPER_ADMIN_IDS: List[int] = []
    BOT_NAME: str = "Yuki"
    WARN_ACTION: str = "mute"  # action on warn-limit reach: "mute" | "ban" | "kick"

    @field_validator("SUPER_ADMIN_IDS", mode="before")
    @classmethod
    def parse_super_admins(cls, v: Union[str, List[int], int, None]) -> List[int]:
        if v is None or v == "":
            return []
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            clean = v.strip("[]() ")
            if not clean:
                return []
            return [int(x.strip()) for x in clean.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        return []


settings = Settings()

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
    BOT_NAME: str = "Aegis"
    WARN_ACTION: str = "mute"  # action on warn-limit reach: "mute" | "ban" | "kick"

    # ── Delivery mode ─────────────────────────────────────────────────────────
    # Long polling is the default (no public URL needed). Set WEBHOOK_URL to a
    # public HTTPS origin to switch to webhooks, which cut latency and let you
    # run several workers behind a load balancer.
    WEBHOOK_URL: str = ""              # e.g. "https://bot.example.com"
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_PORT: int = 8443
    WEBHOOK_SECRET: str = ""           # Telegram secret_token; generated if unset
    LISTEN_HOST: str = "0.0.0.0"

    # Health endpoint for uptime monitors and container healthchecks.
    # Serves GET /health and GET / in both polling and webhook mode. 0 disables.
    HEALTH_PORT: int = 9355

    # ── Shared state ──────────────────────────────────────────────────────────
    # When set, anti-flood counters are shared across every worker so protection
    # survives restarts and horizontal scaling. Empty = per-process memory.
    REDIS_URL: str = ""

    # ── Captcha defaults (per-group overrides live in GroupSettings) ──────────
    CAPTCHA_TIMEOUT_SECONDS: int = 120
    CAPTCHA_ACTION: str = "kick"  # "kick" | "ban"

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

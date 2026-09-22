import os
from typing import List, Optional, Union
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

    # ── Future shared reputation feed (not yet implemented) ───────────────────
    # Empty (the default) means a fully private instance: no outbound calls, no
    # shared state, protection works offline. When the shared feed is built these
    # will let every participating instance pre-warn others about a spam campaign
    # that already hit another instance — the one feature that gets stronger with
    # adoption. Until then no HTTP requests are made.
    #
    # Planned design: send only a salted fingerprint and a pseudonymous group
    # token. Salted fingerprint = HMAC-SHA256(key=SALT, msg=fingerprint).
    REPUTATION_FEED_URL: str = ""       # e.g. "https://feed.example.com"
    REPUTATION_FEED_TOKEN: str = ""     # optional bearer token for private feeds
    REPUTATION_FEED_TIMEOUT: float = 3.0

    # ── Version / update check ────────────────────────────────────────────────
    # Anonymous GET against the public GitHub releases API so a distributed
    # fleet knows when it has drifted. No instance data is sent. Turn it off for
    # air-gapped or privacy-strict deployments; /version still works.
    UPDATE_CHECK_ENABLED: bool = True
    UPDATE_CHECK_REPO: str = "mrsehajofficial/aegis"

    # ── Mini App dashboard (optional) ─────────────────────────────────────────
    # Public HTTPS URL of the dashboard page, used by /dashboard. If the URL has
    # no path (e.g. "https://api.example.com") the "/miniapp" route is appended.
    # The API may live on its own host or even its own account — in that case it
    # only needs the same BOT_TOKEN and DATABASE_URL as the bot.
    MINIAPP_URL: str = ""              # e.g. "https://api.example.com/miniapp"
    # Origin the Mini App calls for API requests. Empty = same origin that served
    # the page (the normal, simplest setup).
    MINIAPP_API_BASE: str = ""         # e.g. "https://api.example.com"
    # BotFather *short name* of the Mini App (Bot Settings → Configure Mini App).
    # Required to build t.me deep links, which are the only form of Mini App
    # button Telegram allows inside group chats.
    MINIAPP_SHORT_NAME: str = ""       # e.g. "dashboard"
    # Overrides the bot username used in deep links; detected automatically.
    MINIAPP_BOT_USERNAME: str = ""
    # Public base URL of the Mini App dashboard (the root HTTPS origin).  Used by
    # the bot to build the /dashboard button link and by the API to resolve
    # relative asset paths.  Set to the deployed origin in production (e.g.
    # "https://aegistelebot.pythonanywhere.com").
    MINIAPP_BASE_URL: str = ""
    # Browser origins allowed to call the API. Only needed when the page and the
    # API are served from different hosts. Comma-separated.
    API_CORS_ORIGINS: List[str] = []

    # Enforce HTTPS at the API layer (redirect HTTP -> HTTPS). Disabled by
    # default; enable behind a TLS-terminating proxy that forwards the original
    # scheme via X-Forwarded-Proto or similar.
    ENABLE_HTTPS_PATH: bool = False

    # Standalone API server (dashboard backend). Off by default: the bot itself
    # never needs it. Turn on to serve the Mini App from this same process.
    API_SERVER_ENABLED: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Mini App request signing. initData older than this window is rejected, so a
    # captured payload cannot be replayed. Set MINIAPP_AUTH_DISABLED=true ONLY for
    # local development — it lets anyone who can reach the API edit group settings.
    MINIAPP_AUTH_MAX_AGE: int = 86400
    MINIAPP_AUTH_DISABLED: bool = False

    # ── HTTP client / proxy ────────────────────────────────────────────────────
    # python-telegram-bot uses httpx internally for all Telegram API calls.
    # httpx auto-detects proxies from HTTP_PROXY / HTTPS_PROXY / ALL_PROXY etc.
    # On some hosts (notably PythonAnywhere) these may be set system-wide and
    # point at a dead proxy, causing every API call to fail with ProxyError.
    # To use a proxy, set HTTP_PROXY_URL below; the application builder will pass
    # it explicitly to httpx.Client(proxies=...).  To go direct (the default),
    # leave this empty and the proxy env vars are cleared at startup.
    HTTP_PROXY_URL: str = ""
    HTTP_CONNECT_TIMEOUT: float = 10.0
    HTTP_READ_TIMEOUT: float = 30.0
    HTTP_WRITE_TIMEOUT: float = 30.0
    HTTP_POOL_SIZE: int = 5

    @field_validator("API_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str], None]) -> List[str]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            clean = v.strip().strip("[]() ")
            if not clean:
                return []
            return [x.strip().strip("\"'") for x in clean.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

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

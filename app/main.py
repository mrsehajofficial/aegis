"""
Aegis — Main entry point for the Telegram Group Management Bot.

Usage:
    python -m app.setup   # first-time interactive .env setup
    uv run python -m app.main
"""
import asyncio
import logging
import os
import secrets
import sys
from pathlib import Path

# Clear any proxy environment variables before httpx is imported anywhere.
# python-telegram-bot uses httpx internally for all Telegram API calls, and
# httpx auto-detects proxies from HTTP_PROXY / HTTPS_PROXY / ALL_PROXY etc.
# On some hosting environments (e.g. PythonAnywhere) these may be set system-
# wide and cause every outbound call to fail with ProxyError.  Clearing them
# here ensures the bot always connects directly.
for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
             "ALL_PROXY", "all_proxy", "no_proxy", "NO_PROXY"):
    os.environ.pop(_var, None)

import httpx

from telegram import BotCommand, BotCommandScopeAllGroupChats
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ChatMemberHandler,
    MessageHandler,
    filters as ptb_filters,
)
from telegram.request import HTTPXRequest

from app.config.settings import settings
from app.bot.application import build_application
from app.bot.health import HealthServer
from app.anti_spam.flood import close_flood_store, init_flood_store
from app.anti_spam.reputation import (
    close_reputation_store,
    init_reputation_store,
)
from app.database.connection import init_db, close_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


async def _start_delivery(app: Application) -> str:
    """
    Start receiving updates, preferring webhooks when a public URL is configured.

    Webhooks remove the polling round-trip and let several workers share one bot,
    which is what makes horizontal scaling possible. Returns the active mode name
    ("webhook" or "polling") so the health endpoint can report it.
    """
    if not settings.WEBHOOK_URL:
        await app.updater.start_polling()
        logger.info("Delivery mode: long polling.")
        return "polling"

    url_path = settings.WEBHOOK_PATH or "/webhook"
    webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}{url_path}"
    # A secret token lets Telegram sign each request; if none is configured we
    # generate one per boot so unauthenticated POSTs are still rejected.
    secret = settings.WEBHOOK_SECRET or secrets.token_urlsafe(24)

    try:
        await app.updater.start_webhook(
            listen=settings.LISTEN_HOST,
            port=settings.WEBHOOK_PORT,
            url_path=url_path,
            webhook_url=webhook_url,
            secret_token=secret,
            drop_pending_updates=False,
        )
    except Exception as e:
        # Usually the optional tornado dependency behind the "webhooks" extra.
        logger.error(
            f"Webhook mode failed to start ({type(e).__name__}: {e}). "
            'Falling back to long polling — install with pip install '
            '"python-telegram-bot[webhooks]" to enable webhooks.'
        )
        await app.updater.start_polling()
        return "polling"

    logger.info(
        f"Delivery mode: webhook. Serving {url_path} on port "
        f"{settings.WEBHOOK_PORT} as {webhook_url}"
    )
    return "webhook"


async def run_bot() -> None:
    """
    Initialize shared state, build the application, and start receiving updates
    over webhooks when configured, otherwise over long polling.
    """
    if not settings.BOT_TOKEN or settings.BOT_TOKEN in ("dummy_token", "123456:REPLACE_ME") or ":" not in settings.BOT_TOKEN:
        logger.error(
            "BOT_TOKEN is missing or a placeholder. Run `python -m app.setup` first "
            "to configure your token from @BotFather (it stays in local .env only)."
        )
        raise SystemExit(2)
    if Path(".env").exists():
        try:
            mode = oct(Path(".env").stat().st_mode & 0o777)
            if mode != "0o600":
                logger.warning(f".env permissions are {mode} — consider `chmod 600 .env`.")
        except OSError:
            pass
    # Initialize database (creates tables if using SQLite; for PostgreSQL, use Alembic)
    if "sqlite" in settings.DATABASE_URL:
        logger.info("Initializing SQLite database...")
        await init_db()
    else:
        logger.info("Using PostgreSQL — ensure Alembic migrations have been run.")

    # Flood counters must be ready before the first message arrives.
    flood_store = await init_flood_store()
    logger.info(f"Flood store backend: {flood_store.name}")

    # The fingerprint network uses the same Redis instance when available.
    rep_store = await init_reputation_store()
    logger.info(f"Reputation store backend: {rep_store.name}")

    logger.info("Building application...")
    app: Application = build_application()

    logger.info(f"Starting bot (token={'***' + settings.BOT_TOKEN[-4:]})...")
    await app.initialize()
    await app.start()

    mode = await _start_delivery(app)

    health: HealthServer | None = None
    if settings.HEALTH_PORT:
        health = HealthServer(
            port=settings.HEALTH_PORT, host=settings.LISTEN_HOST, mode=mode
        )
        try:
            await health.start()
        except Exception as e:
            # A busy port must not stop the bot from serving groups.
            logger.warning(
                f"Could not start the health endpoint on port "
                f"{settings.HEALTH_PORT}: {e}"
            )
            health = None

    try:
        # Run until interrupted
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down...")
    finally:
        logger.info("Stopping bot...")
        if health is not None:
            await health.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await close_flood_store()
        await close_reputation_store()
        await close_db()
        logger.info("Bot shutdown complete.")


def main() -> None:
    """Entry point for running the bot."""
    try:
        asyncio.run(run_bot())
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

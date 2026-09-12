"""
Yuki — Main entry point for the Telegram Group Management Bot.

Usage:
    python -m app.setup   # first-time interactive .env setup
    uv run python -m app.main
"""
import asyncio
import logging
import sys
from pathlib import Path
from telegram.ext import Application

from app.config.settings import settings
from app.bot.application import build_application
from app.database.connection import init_db, close_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    """
    Initialize the database, build the application, and start polling.
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

    logger.info("Building application...")
    app: Application = build_application()

    logger.info(f"Starting bot polling (token={'***' + settings.BOT_TOKEN[-4:]})...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        # Run until interrupted
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down...")
    finally:
        logger.info("Stopping bot...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
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

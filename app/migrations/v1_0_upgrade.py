"""
Database migration script for V1.0.

Run this once to add the new tables and columns introduced in V1.0:
  - blacklists table
  - notes table
  - New columns on group_settings: flood_msg_limit, flood_window_seconds, flood_mute_minutes, spam_action, reports_enabled

Usage:
    .venv/bin/python -m app.migrations.v1_0_upgrade
"""
import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config.settings import settings
from app.database.base import Base
from app.database.models.protection import Blacklist, Note

logger = logging.getLogger(__name__)


async def upgrade():
    engine = create_async_engine(settings.DATABASE_URL)

    # Create new tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Created new tables (blacklists, notes)")

    # Add new columns to group_settings if they don't exist (SQLite-safe)
    async with engine.begin() as conn:
        # Check existing columns
        result = await conn.execute(text("PRAGMA table_info(group_settings)"))
        existing = {row[1] for row in result.fetchall()}

        new_columns = [
            ("flood_msg_limit", "INTEGER DEFAULT 5 NOT NULL"),
            ("flood_window_seconds", "REAL DEFAULT 3.0 NOT NULL"),
            ("flood_mute_minutes", "INTEGER DEFAULT 5 NOT NULL"),
            ("spam_action", "VARCHAR(32) DEFAULT 'delete' NOT NULL"),
            ("reports_enabled", "BOOLEAN DEFAULT 1 NOT NULL"),
        ]

        for col_name, col_def in new_columns:
            if col_name not in existing:
                await conn.execute(
                    text(f"ALTER TABLE group_settings ADD COLUMN {col_name} {col_def}")
                )
                logger.info(f"Added column: {col_name}")
            else:
                logger.info(f"Column already exists: {col_name}")

    await engine.dispose()
    logger.info("V1.0 database upgrade complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(upgrade())
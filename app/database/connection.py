from typing import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import settings
from app.database.base import Base
# Import all models to ensure metadata registration
import app.database.models  # noqa: F401

logger = logging.getLogger(__name__)


def get_async_database_url(url: str) -> str:
    """Ensure proper async driver prefix for PostgreSQL and SQLite."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_url = get_async_database_url(settings.DATABASE_URL)
        engine_args = {
            "echo": settings.LOG_LEVEL.upper() == "DEBUG",
        }
        if "sqlite" in db_url:
            # WAL mode allows one writer + many readers concurrently; busy_timeout
            # prevents "database is locked" when the bot and API share the same file.
            engine_args["connect_args"] = {
                "check_same_thread": False,
                "timeout": 30,
            }
            engine_args["execution_options"] = {
                "isolation_level": "AUTOCOMMIT",
            }
        else:
            engine_args["pool_pre_ping"] = True
            engine_args["pool_size"] = 10
            engine_args["max_overflow"] = 20

        _engine = create_async_engine(db_url, **engine_args)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine()
        _sessionmaker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
    return _sessionmaker


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async session context manager with automatic rollback on error."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Columns added to group_settings after the initial schema (migration 001).
# create_all() never alters existing tables, so pre-existing SQLite databases
# need these backfilled one by one at startup. Every entry carries a NOT NULL-
# safe server default because SQLite's ALTER TABLE ADD COLUMN requires one for
# non-nullable columns. PostgreSQL deployments use the Alembic revisions.
_GROUP_SETTINGS_BACKFILL = {
    "flood_msg_limit": "INTEGER NOT NULL DEFAULT 5",
    "flood_window_seconds": "FLOAT NOT NULL DEFAULT 3.0",
    "flood_mute_minutes": "INTEGER NOT NULL DEFAULT 5",
    "spam_action": "VARCHAR(32) NOT NULL DEFAULT 'delete'",
    "reports_enabled": "BOOLEAN NOT NULL DEFAULT 1",
    "welcome_message": "TEXT",
    "goodbye_message": "TEXT",
    "captcha_enabled": "BOOLEAN NOT NULL DEFAULT 0",
    "captcha_timeout_seconds": "INTEGER NOT NULL DEFAULT 120",
    "captcha_action": "VARCHAR(16) NOT NULL DEFAULT 'kick'",
}


async def _ensure_settings_columns(conn) -> None:
    """SQLite-safe backfill: create_all() does not add columns to existing tables.

    Mirrors the pattern used by app/migrations/v1_0_upgrade.py so pre-existing
    SQLite databases gain every column added since the initial schema without a
    full migration run. PostgreSQL deployments use the Alembic revisions instead.
    Idempotent: only columns missing from the live table are added.
    """
    result = await conn.execute(text("PRAGMA table_info(group_settings)"))
    existing = {row[1] for row in result.fetchall()}
    if not existing:
        return  # table does not exist yet — create_all() builds it complete
    for col, ddl in _GROUP_SETTINGS_BACKFILL.items():
        if col not in existing:
            await conn.execute(text(f"ALTER TABLE group_settings ADD COLUMN {col} {ddl}"))
            logger.info(f"Added missing column group_settings.{col}")


async def init_db() -> None:
    """Initialize database tables (used for SQLite local testing or fresh environments)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_settings_columns(conn)
        # Enable WAL mode for SQLite: allows concurrent reads while writing,
        # and avoids "database is locked" when the bot and API run together.
        db_url = get_async_database_url(settings.DATABASE_URL)
        if "sqlite" in db_url:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))


async def close_db() -> None:
    """Dispose the database engine on shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None

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
            # SQLite concurrency settings
            engine_args["connect_args"] = {"check_same_thread": False}
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


async def _ensure_settings_columns(conn) -> None:
    """SQLite-safe backfill: create_all() does not add columns to existing tables.

    Mirrors the pattern used by app/migrations/v1_0_upgrade.py so pre-existing
    SQLite databases gain the welcome/goodbye message columns without a full
    migration run. PostgreSQL deployments use the Alembic revision instead.
    """
    result = await conn.execute(text("PRAGMA table_info(group_settings)"))
    existing = {row[1] for row in result.fetchall()}
    for col in ("welcome_message", "goodbye_message"):
        if col not in existing:
            await conn.execute(text(f"ALTER TABLE group_settings ADD COLUMN {col} TEXT"))
            logger.info(f"Added missing column group_settings.{col}")


async def init_db() -> None:
    """Initialize database tables (used for SQLite local testing or fresh environments)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_settings_columns(conn)


async def close_db() -> None:
    """Dispose the database engine on shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None

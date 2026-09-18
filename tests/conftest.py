"""
Shared pytest fixtures for the Aegis test suite.

The anti-flood detector and the command rate limiter both read
``time.monotonic()`` and keep module-global state, so their tests need a
controllable clock and a clean store between cases. Keeping the clock here means
the individual test modules stay focused on behaviour.
"""
import pytest

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base


class FakeClock:
    """A monotonic clock that only moves when a test tells it to."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    """A deterministic stand-in for ``time.monotonic()``."""
    return FakeClock()


@pytest.fixture
async def db_session() -> AsyncSession:
    """Provide a clean in-memory SQLite session for database tests."""
    import app.database.models  # noqa: F401 — register all model metadata

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()
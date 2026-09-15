"""
Shared pytest fixtures for the Aegis test suite.

The anti-flood detector and the command rate limiter both read
``time.monotonic()`` and keep module-global state, so their tests need a
controllable clock and a clean store between cases. Keeping the clock here means
the individual test modules stay focused on behaviour.
"""
import pytest


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
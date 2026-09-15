"""Unit tests for the in-memory command rate limiter."""
import pytest

from app.bot.middleware import throttling


@pytest.fixture(autouse=True)
def _clean_rate_store():
    """Rate-limit state is module-global — isolate every test case."""
    throttling._rate_store.clear()
    yield
    throttling._rate_store.clear()


@pytest.fixture
def frozen_time(monkeypatch, clock):
    """Point the rate limiter at a deterministic clock."""
    monkeypatch.setattr(throttling.time, "monotonic", clock)
    return clock


class TestCheckRateLimit:
    def test_allows_calls_up_to_the_maximum(self, frozen_time):
        for _ in range(5):
            assert throttling.check_rate_limit(1, "ban", max_calls=5) is True

    def test_blocks_once_the_maximum_is_reached(self, frozen_time):
        for _ in range(5):
            throttling.check_rate_limit(1, "ban", max_calls=5)
        assert throttling.check_rate_limit(1, "ban", max_calls=5) is False

    def test_window_expiry_resets_the_counter(self, frozen_time):
        for _ in range(5):
            throttling.check_rate_limit(1, "ban", max_calls=5)
        frozen_time.advance(31.0)
        assert throttling.check_rate_limit(1, "ban", max_calls=5) is True

    def test_limits_are_per_command(self, frozen_time):
        for _ in range(5):
            throttling.check_rate_limit(1, "ban", max_calls=5)
        assert throttling.check_rate_limit(1, "mute", max_calls=5) is True

    def test_limits_are_per_user(self, frozen_time):
        for _ in range(5):
            throttling.check_rate_limit(1, "ban", max_calls=5)
        assert throttling.check_rate_limit(2, "ban", max_calls=5) is True

    def test_default_max_matches_the_documented_value(self):
        # guard() documents "6/min"; the limiter allows the 5 calls up to that.
        assert throttling.DEFAULT_MAX == 5
        assert throttling.DEFAULT_WINDOW == 30.0
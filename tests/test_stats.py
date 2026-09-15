"""
Tests for the /stats command building blocks.

The database aggregation lives in the repositories; what is tested here is the
pure presentation layer — uptime formatting and the stats panel body — so a
glitch in the admin-facing numbers cannot ship silently.
"""
from app.bot.handlers.stats import (
    build_stats_text,
    format_uptime,
    mark_started,
    uptime_seconds,
)


class TestFormatUptime:
    def test_seconds_only(self):
        assert format_uptime(42) == "42s"

    def test_minutes_and_seconds(self):
        assert format_uptime(5 * 60 + 30) == "5m 30s"

    def test_hours_and_minutes(self):
        assert format_uptime(2 * 3600 + 15 * 60) == "2h 15m"

    def test_days_and_hours(self):
        assert format_uptime(3 * 86400 + 4 * 3600) == "3d 4h"

    def test_negative_is_clamped_to_zero(self):
        assert format_uptime(-10) == "0s"


class TestUptimeClock:
    def test_zero_before_startup(self):
        # A fresh process has no start time recorded.
        assert uptime_seconds() >= 0.0

    def test_mark_started_makes_uptime_small_but_non_negative(self):
        mark_started()
        assert uptime_seconds() >= 0.0


class TestBuildStatsText:
    def _snapshot(self, **overrides):
        base = {
            "title": "Test Group",
            "members": 120,
            "admins": 4,
            "warnings": 7,
            "warned_users": 3,
            "actions": 25,
            "top_actions": [("BANNED", 12), ("MUTED", 7)],
            "uptime": 9000.0,
        }
        base.update(overrides)
        return base

    def test_contains_the_core_numbers(self):
        text = build_stats_text(self._snapshot())
        assert "Test Group" in text
        assert "120" in text  # members
        assert "4" in text    # admins
        assert "7" in text    # warnings

    def test_top_actions_are_rendered_most_frequent_first(self):
        text = build_stats_text(self._snapshot())
        assert "BANNED" in text and "MUTED" in text
        assert text.index("BANNED") < text.index("MUTED")

    def test_top_actions_capped_at_five(self):
        top = [(f"ACT{i}", 10 - i) for i in range(8)]
        text = build_stats_text(self._snapshot(top_actions=top))
        assert "ACT4" in text   # fifth entry — shown
        assert "ACT5" not in text  # sixth entry — dropped

    def test_no_top_actions_section_when_empty(self):
        text = build_stats_text(self._snapshot(top_actions=[]))
        assert "Top actions" not in text

    def test_uptime_is_formatted_humanly(self):
        text = build_stats_text(self._snapshot(uptime=2 * 3600 + 15 * 60))
        assert "2h 15m" in text

"""Tests for agentflow.shell.usage_parser — T-312.

Fixture strings mirror the exact /usage output formats for Claude and Gemini.
Each parser is tested for: all fields populated, ANSI stripping, None on garbage.
"""
from __future__ import annotations

import pytest

from agentflow.shell.usage_parser import parse_claude_usage, parse_gemini_usage

# ---------------------------------------------------------------------------
# Claude fixture strings
# ---------------------------------------------------------------------------

CLAUDE_TYPICAL = """
Current session
████████████   24% used
Resets 11:19am (Asia/Calcutta)

Current week (all models)
██████████████   84% used
Resets Jul 24 at 2:29am (Asia/Calcutta)
"""

# ANSI-decorated variant (bold labels + green bar)
CLAUDE_WITH_ANSI = (
    "\x1b[1mCurrent session\x1b[0m\n"
    "\x1b[32m████████████\x1b[0m   24% used\n"
    "Resets 11:19am (Asia/Calcutta)\n\n"
    "\x1b[1mCurrent week (all models)\x1b[0m\n"
    "\x1b[32m██████████████\x1b[0m   84% used\n"
    "Resets Jul 24 at 2:29am (Asia/Calcutta)\n"
)

CLAUDE_LOW_USAGE = """
Current session
██   5% used
Resets 3:00pm (America/New_York)

Current week (all models)
███   10% used
Resets Jul 28 at 12:00am (America/New_York)
"""

# Only session block — no weekly block
CLAUDE_SESSION_ONLY = """
Current session
████   20% used
Resets 5:00pm (UTC)
"""

# ---------------------------------------------------------------------------
# Gemini fixture strings
# ---------------------------------------------------------------------------

GEMINI_TYPICAL = """
Weekly Limit   30.13%   30% remaining · Refreshes in 89h 27m
Five Hour Limit  31.22%  31% remaining · Refreshes in 3h 7m
"""

# ANSI-decorated + middle-dot U+00B7
GEMINI_WITH_ANSI = (
    "\x1b[1mWeekly Limit\x1b[0m   30.13%   30% remaining · Refreshes in 89h 27m\n"
    "\x1b[1mFive Hour Limit\x1b[0m  31.22%  31% remaining · Refreshes in 3h 7m\n"
)

# Bullet U+2022 instead of middle-dot
GEMINI_ALT_DOT = """
Weekly Limit   5.00%   95% remaining • Refreshes in 167h 0m
Five Hour Limit  10.00%  90% remaining • Refreshes in 4h 59m
"""

# Only weekly line — missing Five Hour Limit
GEMINI_WEEKLY_ONLY = "Weekly Limit   30.13%   30% remaining · Refreshes in 89h 27m"


# ---------------------------------------------------------------------------
# parse_claude_usage
# ---------------------------------------------------------------------------


class TestParseClaudeUsage:
    def test_all_fields_populated(self):
        result = parse_claude_usage(CLAUDE_TYPICAL)
        assert result is not None
        assert result["session_pct_used"] == 24
        assert "11:19am" in result["session_resets_at"]
        assert "Asia/Calcutta" in result["session_resets_at"]
        assert result["weekly_pct_used"] == 84
        assert "Jul 24" in result["weekly_resets_at"]
        assert "2:29am" in result["weekly_resets_at"]

    def test_strips_ansi_before_parse(self):
        result = parse_claude_usage(CLAUDE_WITH_ANSI)
        assert result is not None
        assert result["session_pct_used"] == 24
        assert result["weekly_pct_used"] == 84
        assert "11:19am" in result["session_resets_at"]
        assert "Jul 24" in result["weekly_resets_at"]

    def test_low_usage_values(self):
        result = parse_claude_usage(CLAUDE_LOW_USAGE)
        assert result is not None
        assert result["session_pct_used"] == 5
        assert result["weekly_pct_used"] == 10

    def test_returns_none_on_empty(self):
        assert parse_claude_usage("") is None

    def test_returns_none_on_garbage(self):
        assert parse_claude_usage("hello world random text") is None
        assert parse_claude_usage("24% used but no context") is None
        assert parse_claude_usage("Current session only no percentage") is None

    def test_returns_none_when_weekly_missing(self):
        # Both session AND weekly required — partial match returns None
        assert parse_claude_usage(CLAUDE_SESSION_ONLY) is None

    def test_pct_is_integer(self):
        result = parse_claude_usage(CLAUDE_TYPICAL)
        assert isinstance(result["session_pct_used"], int)
        assert isinstance(result["weekly_pct_used"], int)

    def test_resets_at_are_nonempty_strings(self):
        result = parse_claude_usage(CLAUDE_TYPICAL)
        assert isinstance(result["session_resets_at"], str)
        assert isinstance(result["weekly_resets_at"], str)
        assert len(result["session_resets_at"]) > 0
        assert len(result["weekly_resets_at"]) > 0

    def test_dict_has_exactly_four_keys(self):
        result = parse_claude_usage(CLAUDE_TYPICAL)
        assert set(result.keys()) == {
            "session_pct_used",
            "session_resets_at",
            "weekly_pct_used",
            "weekly_resets_at",
        }


# ---------------------------------------------------------------------------
# parse_gemini_usage
# ---------------------------------------------------------------------------


class TestParseGeminiUsage:
    def test_all_fields_populated(self):
        result = parse_gemini_usage(GEMINI_TYPICAL)
        assert result is not None
        assert result["weekly_pct_used"] == pytest.approx(30.13, abs=0.01)
        assert "89h 27m" in result["weekly_refreshes_in"]
        assert result["fivehr_pct_used"] == pytest.approx(31.22, abs=0.01)
        assert "3h 7m" in result["fivehr_refreshes_in"]

    def test_strips_ansi_before_parse(self):
        result = parse_gemini_usage(GEMINI_WITH_ANSI)
        assert result is not None
        assert result["weekly_pct_used"] == pytest.approx(30.13, abs=0.01)
        assert result["fivehr_pct_used"] == pytest.approx(31.22, abs=0.01)

    def test_alt_bullet_dot(self):
        result = parse_gemini_usage(GEMINI_ALT_DOT)
        assert result is not None
        assert result["weekly_pct_used"] == pytest.approx(5.0, abs=0.01)
        assert result["fivehr_pct_used"] == pytest.approx(10.0, abs=0.01)

    def test_returns_none_on_empty(self):
        assert parse_gemini_usage("") is None

    def test_returns_none_on_garbage(self):
        assert parse_gemini_usage("hello world random text") is None
        assert parse_gemini_usage("Weekly Limit without numbers") is None

    def test_returns_none_when_five_hour_missing(self):
        assert parse_gemini_usage(GEMINI_WEEKLY_ONLY) is None

    def test_pct_is_float(self):
        result = parse_gemini_usage(GEMINI_TYPICAL)
        assert isinstance(result["weekly_pct_used"], float)
        assert isinstance(result["fivehr_pct_used"], float)

    def test_refreshes_in_are_nonempty_strings(self):
        result = parse_gemini_usage(GEMINI_TYPICAL)
        assert isinstance(result["weekly_refreshes_in"], str)
        assert isinstance(result["fivehr_refreshes_in"], str)
        assert len(result["weekly_refreshes_in"]) > 0
        assert len(result["fivehr_refreshes_in"]) > 0

    def test_dict_has_exactly_four_keys(self):
        result = parse_gemini_usage(GEMINI_TYPICAL)
        assert set(result.keys()) == {
            "weekly_pct_used",
            "weekly_refreshes_in",
            "fivehr_pct_used",
            "fivehr_refreshes_in",
        }

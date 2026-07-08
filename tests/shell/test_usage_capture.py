"""Tests for agentflow.shell.usage_capture — T-163."""
from __future__ import annotations

import json
import os
import select
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentflow.shell.usage_capture import (
    capture_usage,
    parse_usage_output,
    write_usage_to_ledger,
)

# ---------------------------------------------------------------------------
# Sample output
# ---------------------------------------------------------------------------

TYPICAL_OUTPUT = """
Token Usage:
  5-hour window: 18% (56,231 / 310,230 tokens) — resets in 3h 42m
  Weekly window: 5% (15,512 / 310,230 tokens) — resets Jul 14
"""

TYPICAL_OUTPUT_NO_WKLY_TIME = """
Token Usage:
  5-hour window: 7% (21,716 / 310,230 tokens) — resets in 0h 58m
  Weekly window: 2% (6,205 / 310,230 tokens) — resets Jul 14
"""

# ---------------------------------------------------------------------------
# parse_usage_output
# ---------------------------------------------------------------------------


def test_parse_usage_output_typical():
    result = parse_usage_output(TYPICAL_OUTPUT)
    assert result is not None
    assert result["start_pct_5hr"] == 18
    assert result["start_pct_wkly"] == 5
    assert result["cap_5hr"] == 310_230
    assert result["cap_wkly"] == 310_230
    assert result["reset_min_5hr"] == 3 * 60 + 42  # 222


def test_parse_usage_output_typical_no_wkly_time():
    result = parse_usage_output(TYPICAL_OUTPUT_NO_WKLY_TIME)
    assert result is not None
    assert result["start_pct_5hr"] == 7
    assert result["reset_min_5hr"] == 58


def test_parse_usage_output_returns_none_on_garbage():
    assert parse_usage_output("hello world random text") is None
    assert parse_usage_output("") is None
    assert parse_usage_output("Token Usage: no numbers") is None


# ---------------------------------------------------------------------------
# write_usage_to_ledger
# ---------------------------------------------------------------------------

SAMPLE_USAGE = {
    "start_pct_5hr": 10,
    "start_pct_wkly": 3,
    "cap_5hr": 300_000,
    "cap_wkly": 300_000,
    "reset_min_5hr": 180,
    "reset_min_wkly": None,
}


def test_write_usage_to_ledger_creates_file(tmp_path):
    ledger = tmp_path / "ledger.json"
    write_usage_to_ledger(SAMPLE_USAGE, ledger, "session_start")
    assert ledger.exists()
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert "usage_snapshots" in data
    assert len(data["usage_snapshots"]) == 1
    snap = data["usage_snapshots"][0]
    assert snap["label"] == "session_start"
    assert snap["start_pct_5hr"] == 10
    assert "ts" in snap


def test_write_usage_to_ledger_appends(tmp_path):
    ledger = tmp_path / "ledger.json"
    write_usage_to_ledger(SAMPLE_USAGE, ledger, "session_start")
    write_usage_to_ledger(SAMPLE_USAGE, ledger, "session_end")
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert len(data["usage_snapshots"]) == 2
    assert data["usage_snapshots"][0]["label"] == "session_start"
    assert data["usage_snapshots"][1]["label"] == "session_end"


def test_write_usage_to_ledger_preserves_existing_keys(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"sessions": [{"id": "abc"}]}), encoding="utf-8")
    write_usage_to_ledger(SAMPLE_USAGE, ledger, "session_start")
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert "sessions" in data  # pre-existing key kept
    assert len(data["usage_snapshots"]) == 1


# ---------------------------------------------------------------------------
# capture_usage
# ---------------------------------------------------------------------------


def test_capture_usage_mock():
    """capture_usage injects /usage\\r and parses the output."""
    output_bytes = TYPICAL_OUTPUT.encode("utf-8")
    wrapper = MagicMock()
    wrapper.master_fd = 42

    # select returns fd-ready on first call, then raises OSError on os.read second call
    with patch("agentflow.shell.usage_capture.select.select",
               return_value=([42], [], [])):
        with patch("agentflow.shell.usage_capture.os.read",
                   side_effect=[output_bytes, OSError("eof")]):
            result = capture_usage(wrapper, timeout=1.0)

    wrapper.write_input.assert_called_once_with("/usage\r")
    assert result is not None
    assert result["start_pct_5hr"] == 18
    assert result["start_pct_wkly"] == 5


def test_capture_usage_returns_none_on_no_output():
    """If select never returns ready, capture_usage returns None."""
    wrapper = MagicMock()
    wrapper.master_fd = 99

    with patch("agentflow.shell.usage_capture.select.select",
               return_value=([], [], [])):
        # Loop drains quickly since remaining→0; use tiny timeout
        result = capture_usage(wrapper, timeout=0.05)

    assert result is None


def test_capture_usage_returns_none_on_write_error():
    """If write_input raises, capture_usage silently returns None."""
    wrapper = MagicMock()
    wrapper.write_input.side_effect = OSError("broken pipe")
    result = capture_usage(wrapper, timeout=1.0)
    assert result is None

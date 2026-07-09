"""Tests for agentflow.shadow.headroom_ab — record and compute headroom A/B metrics.

Verifies record_output() appends JSONL entries and compute_delta() computes
per-arm stats (mean, n) and delta (mean_on - mean_off).
"""

from __future__ import annotations

import json
from pathlib import Path


def test_record_output_appends_jsonl(tmp_path):
    """record_output appends {ts, arm, output_tokens} to headroom_ab_log.jsonl."""
    from agentflow.shadow.headroom_ab import record_output

    record_output(tmp_path, arm="on", output_tokens=123)

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    assert log_path.exists()

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["arm"] == "on"
    assert entry["output_tokens"] == 123
    assert "ts" in entry


def test_record_output_appends_multiple_entries(tmp_path):
    """Multiple calls to record_output append to the same file."""
    from agentflow.shadow.headroom_ab import record_output

    record_output(tmp_path, arm="on", output_tokens=100)
    record_output(tmp_path, arm="off", output_tokens=200)
    record_output(tmp_path, arm="on", output_tokens=150)

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 3

    entries = [json.loads(line) for line in lines]
    assert entries[0]["arm"] == "on"
    assert entries[0]["output_tokens"] == 100
    assert entries[1]["arm"] == "off"
    assert entries[1]["output_tokens"] == 200
    assert entries[2]["arm"] == "on"
    assert entries[2]["output_tokens"] == 150


def test_record_output_with_custom_ts(tmp_path):
    """record_output accepts optional ts parameter."""
    from agentflow.shadow.headroom_ab import record_output

    custom_ts = "2026-07-09T10:00:00"
    record_output(tmp_path, arm="on", output_tokens=123, ts=custom_ts)

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    entry = json.loads(log_path.read_text().strip())
    assert entry["ts"] == custom_ts


def test_record_output_creates_directory(tmp_path):
    """record_output creates .agentflow directory if it doesn't exist."""
    from agentflow.shadow.headroom_ab import record_output

    # Ensure directory doesn't exist
    assert not (tmp_path / ".agentflow").exists()

    record_output(tmp_path, arm="on", output_tokens=123)

    assert (tmp_path / ".agentflow").exists()


def test_compute_delta_correct_stats():
    """compute_delta returns correct mean, n, and delta for on/off arms."""
    from agentflow.shadow.headroom_ab import compute_delta, record_output
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Record 2 "on" entries: 100, 200 (mean = 150)
        record_output(tmp_path, arm="on", output_tokens=100)
        record_output(tmp_path, arm="on", output_tokens=200)

        # Record 2 "off" entries: 300, 400 (mean = 350)
        record_output(tmp_path, arm="off", output_tokens=300)
        record_output(tmp_path, arm="off", output_tokens=400)

        result = compute_delta(tmp_path)

        assert result["on"]["mean"] == 150.0
        assert result["on"]["n"] == 2
        assert result["off"]["mean"] == 350.0
        assert result["off"]["n"] == 2
        # delta = mean_on - mean_off = 150 - 350 = -200
        assert result["delta"] == -200.0


def test_compute_delta_single_entry_per_arm():
    """compute_delta works with single entries per arm."""
    from agentflow.shadow.headroom_ab import compute_delta, record_output
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        record_output(tmp_path, arm="on", output_tokens=100)
        record_output(tmp_path, arm="off", output_tokens=200)

        result = compute_delta(tmp_path)

        assert result["on"]["mean"] == 100.0
        assert result["on"]["n"] == 1
        assert result["off"]["mean"] == 200.0
        assert result["off"]["n"] == 1
        assert result["delta"] == -100.0


def test_compute_delta_empty_log():
    """compute_delta returns zeros when log is absent or empty."""
    from agentflow.shadow.headroom_ab import compute_delta
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # No log file created
        result = compute_delta(tmp_path)

        assert result["on"]["mean"] == 0.0
        assert result["on"]["n"] == 0
        assert result["off"]["mean"] == 0.0
        assert result["off"]["n"] == 0
        assert result["delta"] is None


def test_compute_delta_only_on_arm():
    """compute_delta handles case where only 'on' arm has data."""
    from agentflow.shadow.headroom_ab import compute_delta, record_output
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        record_output(tmp_path, arm="on", output_tokens=100)
        record_output(tmp_path, arm="on", output_tokens=200)

        result = compute_delta(tmp_path)

        assert result["on"]["mean"] == 150.0
        assert result["on"]["n"] == 2
        assert result["off"]["mean"] == 0.0
        assert result["off"]["n"] == 0
        # delta should be None or handle the case appropriately
        assert result["delta"] is None or isinstance(result["delta"], float)


def test_compute_delta_only_off_arm():
    """compute_delta handles case where only 'off' arm has data."""
    from agentflow.shadow.headroom_ab import compute_delta, record_output
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        record_output(tmp_path, arm="off", output_tokens=300)
        record_output(tmp_path, arm="off", output_tokens=400)

        result = compute_delta(tmp_path)

        assert result["on"]["mean"] == 0.0
        assert result["on"]["n"] == 0
        assert result["off"]["mean"] == 350.0
        assert result["off"]["n"] == 2
        # delta should be None or handle the case appropriately
        assert result["delta"] is None or isinstance(result["delta"], float)


def test_compute_delta_returns_dict_structure():
    """compute_delta returns dict with on, off, and delta keys."""
    from agentflow.shadow.headroom_ab import compute_delta, record_output
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        record_output(tmp_path, arm="on", output_tokens=100)

        result = compute_delta(tmp_path)

        assert isinstance(result, dict)
        assert "on" in result
        assert "off" in result
        assert "delta" in result
        assert isinstance(result["on"], dict)
        assert isinstance(result["off"], dict)
        assert "mean" in result["on"]
        assert "n" in result["on"]
        assert "mean" in result["off"]
        assert "n" in result["off"]

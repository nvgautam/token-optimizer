"""Tests for agentflow.shadow.headroom_ab — record and compute headroom A/B metrics.

Verifies record_compression() appends JSONL entries and compute_delta() computes
per-arm stats (mean, n) on tokens_before and delta (mean_on - mean_off).
"""

from __future__ import annotations

import json
from pathlib import Path


def test_record_compression_appends_jsonl(tmp_path):
    """record_compression appends {ts, arm, tokens_before, tokens_after} to headroom_ab_log.jsonl."""
    from agentflow.shadow.headroom_ab import record_compression

    record_compression(tmp_path, arm="on", tokens_before=123, tokens_after=80)

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    assert log_path.exists()

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["arm"] == "on"
    assert entry["tokens_before"] == 123
    assert entry["tokens_after"] == 80
    assert "ts" in entry


def test_record_compression_appends_multiple_entries(tmp_path):
    """Multiple calls to record_compression append to the same file."""
    from agentflow.shadow.headroom_ab import record_compression

    record_compression(tmp_path, arm="on", tokens_before=100, tokens_after=60)
    record_compression(tmp_path, arm="off", tokens_before=0, tokens_after=0)
    record_compression(tmp_path, arm="on", tokens_before=150, tokens_after=90)

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 3

    entries = [json.loads(line) for line in lines]
    assert entries[0]["arm"] == "on"
    assert entries[0]["tokens_before"] == 100
    assert entries[1]["arm"] == "off"
    assert entries[1]["tokens_before"] == 0
    assert entries[2]["arm"] == "on"
    assert entries[2]["tokens_before"] == 150


def test_record_compression_with_custom_ts(tmp_path):
    """record_compression accepts optional ts parameter."""
    from agentflow.shadow.headroom_ab import record_compression

    custom_ts = "2026-07-09T10:00:00"
    record_compression(tmp_path, arm="on", tokens_before=123, tokens_after=80, ts=custom_ts)

    log_path = tmp_path / ".agentflow" / "headroom_ab_log.jsonl"
    entry = json.loads(log_path.read_text().strip())
    assert entry["ts"] == custom_ts


def test_record_compression_creates_directory(tmp_path):
    """record_compression creates .agentflow directory if it doesn't exist."""
    from agentflow.shadow.headroom_ab import record_compression

    assert not (tmp_path / ".agentflow").exists()
    record_compression(tmp_path, arm="on", tokens_before=123, tokens_after=80)
    assert (tmp_path / ".agentflow").exists()


def test_compute_delta_correct_stats(tmp_path):
    """compute_delta returns correct mean, n on tokens_before and delta for on/off arms."""
    from agentflow.shadow.headroom_ab import compute_delta, record_compression

    record_compression(tmp_path, arm="on", tokens_before=100, tokens_after=60)
    record_compression(tmp_path, arm="on", tokens_before=200, tokens_after=120)
    record_compression(tmp_path, arm="off", tokens_before=300, tokens_after=0)
    record_compression(tmp_path, arm="off", tokens_before=400, tokens_after=0)

    result = compute_delta(tmp_path)

    assert result["on"]["mean"] == 150.0
    assert result["on"]["n"] == 2
    assert result["off"]["mean"] == 350.0
    assert result["off"]["n"] == 2
    assert result["delta"] == -200.0


def test_compute_delta_single_entry_per_arm(tmp_path):
    """compute_delta works with single entries per arm."""
    from agentflow.shadow.headroom_ab import compute_delta, record_compression

    record_compression(tmp_path, arm="on", tokens_before=100, tokens_after=60)
    record_compression(tmp_path, arm="off", tokens_before=200, tokens_after=0)

    result = compute_delta(tmp_path)

    assert result["on"]["mean"] == 100.0
    assert result["on"]["n"] == 1
    assert result["off"]["mean"] == 200.0
    assert result["off"]["n"] == 1
    assert result["delta"] == -100.0


def test_compute_delta_empty_log(tmp_path):
    """compute_delta returns zeros and None delta when log is absent."""
    from agentflow.shadow.headroom_ab import compute_delta

    result = compute_delta(tmp_path)

    assert result["on"]["mean"] == 0.0
    assert result["on"]["n"] == 0
    assert result["off"]["mean"] == 0.0
    assert result["off"]["n"] == 0
    assert result["delta"] is None


def test_compute_delta_only_on_arm(tmp_path):
    """compute_delta returns None delta when only 'on' arm has data."""
    from agentflow.shadow.headroom_ab import compute_delta, record_compression

    record_compression(tmp_path, arm="on", tokens_before=100, tokens_after=60)
    record_compression(tmp_path, arm="on", tokens_before=200, tokens_after=120)

    result = compute_delta(tmp_path)

    assert result["on"]["mean"] == 150.0
    assert result["on"]["n"] == 2
    assert result["off"]["mean"] == 0.0
    assert result["off"]["n"] == 0
    assert result["delta"] is None


def test_compute_delta_only_off_arm(tmp_path):
    """compute_delta returns None delta when only 'off' arm has data."""
    from agentflow.shadow.headroom_ab import compute_delta, record_compression

    record_compression(tmp_path, arm="off", tokens_before=300, tokens_after=0)
    record_compression(tmp_path, arm="off", tokens_before=400, tokens_after=0)

    result = compute_delta(tmp_path)

    assert result["on"]["mean"] == 0.0
    assert result["on"]["n"] == 0
    assert result["off"]["mean"] == 350.0
    assert result["off"]["n"] == 2
    assert result["delta"] is None


def test_compute_delta_returns_dict_structure(tmp_path):
    """compute_delta returns dict with on, off, and delta keys."""
    from agentflow.shadow.headroom_ab import compute_delta, record_compression

    record_compression(tmp_path, arm="on", tokens_before=100, tokens_after=60)

    result = compute_delta(tmp_path)

    assert isinstance(result, dict)
    assert "on" in result and "off" in result and "delta" in result
    assert isinstance(result["on"], dict) and isinstance(result["off"], dict)
    assert "mean" in result["on"] and "n" in result["on"]
    assert "mean" in result["off"] and "n" in result["off"]


def test_compute_delta_skips_truncated_lines(tmp_path):
    """compute_delta skips lines that fail JSON parsing (CRITICAL #3)."""
    from agentflow.shadow.headroom_ab import compute_delta, record_compression, _ab_log_path

    record_compression(tmp_path, arm="on", tokens_before=100, tokens_after=60)

    log_path = _ab_log_path(tmp_path)
    with open(log_path, "a") as fh:
        fh.write('{"arm": "on", "tokens_before": 200, "tokens_after": 1\n')  # truncated

    result = compute_delta(tmp_path)

    assert result["on"]["n"] == 1
    assert result["on"]["mean"] == 100.0

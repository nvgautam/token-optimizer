"""Tests for verbosity_ab_analysis module."""

import json
import tempfile
from pathlib import Path

import pytest

from agentflow.shadow.verbosity_ab_analysis import (
    compute_arm_stats,
    load_arm_entries,
    load_baseline,
    run_ab_comparison,
)
from agentflow.shadow.verbosity_ab import record_turn


class TestComputeArmStats:
    def test_compute_arm_stats_empty(self):
        """Empty list returns zero-n stats dict."""
        result = compute_arm_stats([])
        assert result["n"] == 0
        assert result["mean"] == 0.0
        assert result["p90"] == 0.0
        assert result["ci95_low"] is None
        assert result["ci95_high"] is None

    def test_compute_arm_stats_with_data(self):
        """Correct mean, p90, n for non-empty data."""
        tokens = [100, 200, 300, 400, 500]
        result = compute_arm_stats(tokens)
        assert result["n"] == 5
        assert result["mean"] == 300.0
        # p90 for n=5: index min(int(5*0.9), 4) = min(4, 4) = 4 -> tokens[4] = 500
        assert result["p90"] == 500
        assert result["ci95_low"] is not None
        assert result["ci95_high"] is not None

    def test_compute_arm_stats_single_element(self):
        """Single element: no CI (n < 2)."""
        result = compute_arm_stats([100])
        assert result["n"] == 1
        assert result["mean"] == 100.0
        assert result["p90"] == 100
        assert result["ci95_low"] is None
        assert result["ci95_high"] is None


class TestLoadArmEntries:
    def test_load_arm_entries_filters_by_arm(self):
        """Only returns entries for the requested arm."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Record entries in both arms
            record_turn(root, "test", 1, 100, "on", ts="2026-01-01T00:00:00")
            record_turn(root, "test", 2, 200, "off", ts="2026-01-01T00:00:01")
            record_turn(root, "test", 3, 150, "on", ts="2026-01-01T00:00:02")

            on_entries = load_arm_entries(root, "on")
            off_entries = load_arm_entries(root, "off")

            assert len(on_entries) == 2
            assert all(e["arm"] == "on" for e in on_entries)
            assert len(off_entries) == 1
            assert all(e["arm"] == "off" for e in off_entries)

    def test_load_arm_entries_empty_log(self):
        """Returns empty list when log does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = load_arm_entries(root, "on")
            assert entries == []


class TestRunAbComparison:
    def test_run_ab_comparison_creates_baseline_file(self):
        """Creates .agentflow/verbosity_baseline.json."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Record some entries
            record_turn(root, "test", 1, 100, "on")
            record_turn(root, "test", 2, 200, "off")
            record_turn(root, "test", 3, 150, "off")

            result = run_ab_comparison(root)

            baseline_path = root / ".agentflow" / "verbosity_baseline.json"
            assert baseline_path.exists()

            # Verify content
            assert result["measured"] is True
            assert result["arms"]["off"]["n"] == 2
            assert result["arms"]["on"]["n"] == 1

    def test_run_ab_comparison_with_session_type_filter(self):
        """Only entries matching session_type are used."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_turn(root, "session_a", 1, 100, "on")
            record_turn(root, "session_b", 1, 200, "on")
            record_turn(root, "session_a", 1, 150, "off")

            result = run_ab_comparison(root, session_type="session_a")

            # Only session_a entries should be included
            assert result["arms"]["on"]["n"] == 1
            assert result["arms"]["off"]["n"] == 1

    def test_run_ab_comparison_stopping_criterion(self):
        """Stopping criterion met when n >= 20 for both arms, CI < 100."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Generate 20 'on' entries
            for i in range(20):
                record_turn(root, "test", i, 200 + i, "on")
            # Generate 20 'off' entries with small variance (CI < 100)
            for i in range(20):
                record_turn(root, "test", 100 + i, 250 + i, "off")

            result = run_ab_comparison(root)

            assert result["stopping_met"] is True
            assert "VERBOSITY A/B COMPLETE" in result["stopping_status"]


class TestLoadBaseline:
    def test_load_baseline_returns_fallback_when_absent(self):
        """No baseline file returns unmeasured fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = load_baseline(root)

            assert result["measured"] is False
            assert result["baseline_tokens"] == 600
            assert result["sample_size"] == 0
            assert result["stopping_met"] is False

    def test_load_baseline_reads_existing_file(self):
        """Reads and returns existing baseline file."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create a baseline file
            baseline_path = root / ".agentflow" / "verbosity_baseline.json"
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_data = {
                "computed_at": "2026-01-01T00:00:00",
                "baseline_tokens": 250,
                "sample_size": 20,
                "ci95_low": 240.0,
                "ci95_high": 260.0,
                "measured": True,
                "arms": {},
                "stopping_met": True,
                "stopping_status": "COMPLETE",
            }
            baseline_path.write_text(json.dumps(baseline_data))

            result = load_baseline(root)

            assert result["measured"] is True
            assert result["baseline_tokens"] == 250
            assert result["sample_size"] == 20

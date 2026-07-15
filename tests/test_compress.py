"""Tests for agentflow.proxy.compress module."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from agentflow.proxy.compress import _is_mid_round


class TestIsMidRound:
    """Tests for _is_mid_round() with SID-aware path resolution."""

    def test_is_mid_round_with_sid_reads_sid_path(self, tmp_path, monkeypatch):
        """With AGENTFLOW_SESSION_ID set, read from sessions/<SID>/tasks_in_flight.json."""
        # Set the environment variable to a test SID
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-sid")

        # Create the SID-scoped tasks_in_flight.json
        sid_dir = tmp_path / ".agentflow" / "sessions" / "test-sid"
        sid_dir.mkdir(parents=True, exist_ok=True)
        tif_path = sid_dir / "tasks_in_flight.json"
        tif_path.write_text(json.dumps(["T-001"]), encoding="utf-8")

        # No flat file present
        flat_path = tmp_path / ".agentflow" / "tasks_in_flight.json"
        assert not flat_path.exists()

        # Verify _is_mid_round returns True
        assert _is_mid_round(tmp_path) is True

    def test_is_mid_round_no_sid_reads_flat_path(self, tmp_path, monkeypatch):
        """Without AGENTFLOW_SESSION_ID, read from flat .agentflow/tasks_in_flight.json."""
        # Ensure env var is not set
        monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

        # Create the flat tasks_in_flight.json
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        flat_path = agentflow_dir / "tasks_in_flight.json"
        flat_path.write_text(json.dumps(["T-001"]), encoding="utf-8")

        # Verify _is_mid_round returns True
        assert _is_mid_round(tmp_path) is True

    def test_is_mid_round_flat_absent_with_sid_returns_false(self, tmp_path, monkeypatch):
        """With AGENTFLOW_SESSION_ID set but no SID tasks file, return False (no fallback)."""
        # Set the environment variable to a test SID
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-sid")

        # Create agentflow_dir but NOT the SID-scoped tasks_in_flight
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)

        # Ensure flat file is absent
        flat_path = agentflow_dir / "tasks_in_flight.json"
        assert not flat_path.exists()

        # Verify _is_mid_round returns False (no fallback to flat)
        assert _is_mid_round(tmp_path) is False

    def test_is_mid_round_empty_sid_tasks_returns_false(self, tmp_path, monkeypatch):
        """With AGENTFLOW_SESSION_ID set and empty tasks file, return False."""
        monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-sid")

        sid_dir = tmp_path / ".agentflow" / "sessions" / "test-sid"
        sid_dir.mkdir(parents=True, exist_ok=True)
        tif_path = sid_dir / "tasks_in_flight.json"
        tif_path.write_text(json.dumps([]), encoding="utf-8")

        # Verify _is_mid_round returns False (empty list is falsy)
        assert _is_mid_round(tmp_path) is False

    def test_is_mid_round_malformed_json_returns_false(self, tmp_path, monkeypatch):
        """With malformed JSON, return False."""
        monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        flat_path = agentflow_dir / "tasks_in_flight.json"
        flat_path.write_text("not valid json", encoding="utf-8")

        assert _is_mid_round(tmp_path) is False

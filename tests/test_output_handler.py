"""Tests for output_handler._read_fill_tokens with per-SID path support."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
import pytest

from agentflow.shell.output_handler import _read_fill_tokens
from agentflow.hooks.stop_context_capture import FILL_STALE_SECONDS


def test_read_fill_tokens_uses_sid_path(tmp_path, monkeypatch):
    """With AGENTFLOW_SESSION_ID=abc123, _read_fill_tokens should read from sessions/abc123/ path."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Set environment variable
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc123")

    # Create per-SID context_fill.json
    sid_dir = agentflow_dir / "sessions" / "abc123"
    sid_dir.mkdir(parents=True, exist_ok=True)
    sid_path = sid_dir / "context_fill.json"
    sid_path.write_text(json.dumps({"fill_tokens": 75000, "ts": time.time()}))

    # Ensure root-level file doesn't exist (or has different content)
    root_path = agentflow_dir / "context_fill.json"
    if root_path.exists():
        root_path.unlink()

    result = _read_fill_tokens(tmp_path)
    assert result == 75000


def test_read_fill_tokens_uses_legacy_path_without_sid(tmp_path, monkeypatch):
    """Without AGENTFLOW_SESSION_ID, _read_fill_tokens should read from root-level path (legacy)."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Ensure no environment variable
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)

    # Create root-level context_fill.json
    root_path = agentflow_dir / "context_fill.json"
    root_path.write_text(json.dumps({"fill_tokens": 85000, "ts": time.time()}))

    result = _read_fill_tokens(tmp_path)
    assert result == 85000


def test_read_fill_tokens_returns_none_when_file_absent(tmp_path, monkeypatch):
    """When context_fill.json is absent, _read_fill_tokens should return None."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc123")

    # Don't create the file
    result = _read_fill_tokens(tmp_path)
    assert result is None


def test_read_fill_tokens_returns_none_when_stale(tmp_path, monkeypatch):
    """When context_fill.json is stale (> FILL_STALE_SECONDS old), return None."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc123")

    # Create with old timestamp
    sid_dir = agentflow_dir / "sessions" / "abc123"
    sid_dir.mkdir(parents=True, exist_ok=True)
    old_ts = time.time() - FILL_STALE_SECONDS - 10  # Older than stale threshold
    sid_path = sid_dir / "context_fill.json"
    sid_path.write_text(json.dumps({"fill_tokens": 75000, "ts": old_ts}))

    result = _read_fill_tokens(tmp_path)
    assert result is None


def test_read_fill_tokens_returns_none_on_malformed_json(tmp_path, monkeypatch):
    """When context_fill.json is malformed, return None."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "abc123")

    # Create with malformed JSON
    sid_dir = agentflow_dir / "sessions" / "abc123"
    sid_dir.mkdir(parents=True, exist_ok=True)
    sid_path = sid_dir / "context_fill.json"
    sid_path.write_text("{ invalid json }")

    result = _read_fill_tokens(tmp_path)
    assert result is None


def test_read_fill_tokens_empty_sid_env_uses_legacy_path(tmp_path, monkeypatch):
    """When AGENTFLOW_SESSION_ID is empty string, should use legacy path."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)

    # Set to empty string
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "")

    # Create root-level file
    root_path = agentflow_dir / "context_fill.json"
    root_path.write_text(json.dumps({"fill_tokens": 90000, "ts": time.time()}))

    result = _read_fill_tokens(tmp_path)
    assert result == 90000

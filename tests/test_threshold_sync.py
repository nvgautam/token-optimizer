"""Unit tests for threshold_sync.sync_session_type() with per-SID session state."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentflow.shell.threshold_sync import sync_session_type


def _make_manager(project_root: Path):
    """Create a mock manager with required attributes."""
    manager = MagicMock()
    manager._project_root = project_root
    manager.session_type = None
    manager._config = {
        "oracle_threshold_tokens": 50000,
        "handoff_primary_tokens": 80000,
    }
    # Mock the state machine's threshold_tokens
    manager._state_machine = MagicMock()
    manager._state_machine.threshold_tokens = 0
    return manager


def test_sync_session_type_reads_sid_scoped_path(tmp_path, monkeypatch):
    """SID set, sessions/<SID>/session_state.json has session_type → apply it."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test_sid_123")
    manager = _make_manager(tmp_path)

    # Create the per-SID session_state.json
    agentflow_dir = tmp_path / ".agentflow"
    sessions_dir = agentflow_dir / "sessions" / "test_sid_123"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    session_state_file = sessions_dir / "session_state.json"
    session_state_file.write_text(json.dumps({"session_type": "orchestrator"}))

    # Act
    sync_session_type(manager)

    # Assert
    assert manager.session_type == "orchestrator"
    assert manager._state_machine.threshold_tokens == 80000


def test_sync_session_type_falls_back_to_root_session_state(tmp_path, monkeypatch):
    """No SID set, root session_state.json exists → use it."""
    # Setup
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    manager = _make_manager(tmp_path)

    # Create only root-level session_state.json
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    root_session_state = agentflow_dir / "session_state.json"
    root_session_state.write_text(json.dumps({"session_type": "oracle"}))

    # Act
    sync_session_type(manager)

    # Assert
    assert manager.session_type == "oracle"
    assert manager._state_machine.threshold_tokens == 50000


def test_sync_session_type_falls_back_to_session_type_file(tmp_path, monkeypatch):
    """No SID set, both JSON files absent, root session_type file exists → read it."""
    # Setup
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    manager = _make_manager(tmp_path)

    # Create only the legacy session_type file (no JSON files)
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    session_type_file = agentflow_dir / "session_type"
    session_type_file.write_text("orchestrator\n")

    # Act
    sync_session_type(manager)

    # Assert
    assert manager.session_type == "orchestrator"
    assert manager._state_machine.threshold_tokens == 80000


def test_sync_session_type_no_sid_uses_root_files(tmp_path, monkeypatch):
    """No SID in env → check root-level files only (skip per-SID path)."""
    # Setup
    monkeypatch.delenv("AGENTFLOW_SESSION_ID", raising=False)
    manager = _make_manager(tmp_path)

    # Create root-level session_state.json
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    root_session_state = agentflow_dir / "session_state.json"
    root_session_state.write_text(json.dumps({"session_type": "oracle"}))

    # Act
    sync_session_type(manager)

    # Assert
    assert manager.session_type == "oracle"
    assert manager._state_machine.threshold_tokens == 50000


def test_sync_session_type_old_root_sid_file_not_used(tmp_path, monkeypatch):
    """Old pattern session_state_<SID>.json at root is ignored now."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "old_sid")
    manager = _make_manager(tmp_path)

    # Create ONLY the old root-level pattern (session_state_<SID>.json)
    # This should NOT be read anymore
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    old_pattern_file = agentflow_dir / "session_state_old_sid.json"
    old_pattern_file.write_text(json.dumps({"session_type": "orchestrator"}))

    # Act
    sync_session_type(manager)

    # Assert: session_type should NOT be set (file should not be read)
    # apply_session_threshold should be called with no session_type set
    assert manager.session_type is None
    # When session_type is None, apply_session_threshold returns early
    assert manager._state_machine.threshold_tokens == 0


def test_sync_session_type_priority_sid_over_root(tmp_path, monkeypatch):
    """Per-SID file takes priority over root files when both exist."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "priority_sid")
    manager = _make_manager(tmp_path)

    # Create both per-SID and root files (different values)
    agentflow_dir = tmp_path / ".agentflow"
    sessions_dir = agentflow_dir / "sessions" / "priority_sid"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Per-SID: orchestrator
    sid_session_state = sessions_dir / "session_state.json"
    sid_session_state.write_text(json.dumps({"session_type": "orchestrator"}))

    # Root: oracle
    root_session_state = agentflow_dir / "session_state.json"
    root_session_state.write_text(json.dumps({"session_type": "oracle"}))

    # Act
    sync_session_type(manager)

    # Assert: should use per-SID value
    assert manager.session_type == "orchestrator"
    assert manager._state_machine.threshold_tokens == 80000


def test_sync_session_type_invalid_json_skips(tmp_path, monkeypatch):
    """Invalid JSON in session_state.json should be skipped without falling back to root when SID is present."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "invalid_json_sid")
    manager = _make_manager(tmp_path)

    # Create per-SID with invalid JSON, root with valid JSON
    agentflow_dir = tmp_path / ".agentflow"
    sessions_dir = agentflow_dir / "sessions" / "invalid_json_sid"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Per-SID: invalid JSON
    sid_session_state = sessions_dir / "session_state.json"
    sid_session_state.write_text("{invalid json}")

    # Root: valid JSON
    root_session_state = agentflow_dir / "session_state.json"
    root_session_state.write_text(json.dumps({"session_type": "oracle"}))

    # Act
    sync_session_type(manager)

    # Assert: should NOT fall back to root
    assert manager.session_type is None
    assert manager._state_machine.threshold_tokens == 0


def test_sync_session_type_missing_session_type_key(tmp_path, monkeypatch):
    """JSON without session_type key should be skipped without falling back when SID is present."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "missing_key_sid")
    manager = _make_manager(tmp_path)

    # Create per-SID without session_type key, root with valid JSON
    agentflow_dir = tmp_path / ".agentflow"
    sessions_dir = agentflow_dir / "sessions" / "missing_key_sid"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Per-SID: no session_type key
    sid_session_state = sessions_dir / "session_state.json"
    sid_session_state.write_text(json.dumps({"other_key": "value"}))

    # Root: valid JSON
    root_session_state = agentflow_dir / "session_state.json"
    root_session_state.write_text(json.dumps({"session_type": "orchestrator"}))

    # Act
    sync_session_type(manager)

    # Assert: should NOT fall back to root
    assert manager.session_type is None
    assert manager._state_machine.threshold_tokens == 0


def test_sync_session_type_invalid_value_skips(tmp_path, monkeypatch):
    """Invalid session_type value should be skipped without falling back when SID is present."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "invalid_val_sid")
    manager = _make_manager(tmp_path)

    # Create per-SID with invalid session_type, root with valid JSON
    agentflow_dir = tmp_path / ".agentflow"
    sessions_dir = agentflow_dir / "sessions" / "invalid_val_sid"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Per-SID: invalid session_type value
    sid_session_state = sessions_dir / "session_state.json"
    sid_session_state.write_text(json.dumps({"session_type": "invalid_type"}))

    # Root: valid JSON
    root_session_state = agentflow_dir / "session_state.json"
    root_session_state.write_text(json.dumps({"session_type": "oracle"}))

    # Act
    sync_session_type(manager)

    # Assert: should NOT fall back to root
    assert manager.session_type is None
    assert manager._state_machine.threshold_tokens == 0


def test_sync_session_type_no_files_applies_threshold(tmp_path, monkeypatch):
    """No session files → apply_session_threshold called with session_type=None."""
    # Setup
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "no_files_sid")
    manager = _make_manager(tmp_path)

    # Create agentflow dir but no state files
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    # Act
    sync_session_type(manager)

    # Assert: session_type should remain None
    assert manager.session_type is None
    # apply_session_threshold should return early when session_type is None
    assert manager._state_machine.threshold_tokens == 0

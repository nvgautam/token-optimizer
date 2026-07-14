from pathlib import Path
import pytest

from agentflow.shell.session_paths import session_file


def test_session_file_with_sid(tmp_path):
    """Session file with SID should create sessions/<sid>/ directory and return correct path."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    sid = "abc123"
    result = session_file(agentflow_dir, "context_fill.json", sid=sid)

    # Check the returned path is correct
    expected = agentflow_dir / "sessions" / sid / "context_fill.json"
    assert result == expected

    # Check the directory was created
    assert (agentflow_dir / "sessions" / sid).exists()
    assert (agentflow_dir / "sessions" / sid).is_dir()


def test_session_file_without_sid(tmp_path):
    """Session file without SID should return legacy fallback path (no sessions/ dir)."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    result = session_file(agentflow_dir, "context_fill.json", sid=None)

    # Check the returned path is correct
    expected = agentflow_dir / "context_fill.json"
    assert result == expected

    # Check no sessions/ dir was created
    assert not (agentflow_dir / "sessions").exists()


def test_session_file_empty_sid(tmp_path):
    """Session file with empty SID should be treated as no SID (legacy fallback)."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    result = session_file(agentflow_dir, "context_fill.json", sid="")

    # Check the returned path is correct (same as None)
    expected = agentflow_dir / "context_fill.json"
    assert result == expected

    # Check no sessions/ dir was created
    assert not (agentflow_dir / "sessions").exists()


def test_session_file_creates_parent_dir(tmp_path):
    """Session file should create parent directories (parents=True, exist_ok=True)."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    sid = "deep_nested_sid"
    # Directory should not exist yet
    assert not (agentflow_dir / "sessions" / sid).exists()

    result = session_file(agentflow_dir, "nested_file.json", sid=sid)

    # After call, directory should exist
    assert (agentflow_dir / "sessions" / sid).exists()
    assert (agentflow_dir / "sessions" / sid).is_dir()


def test_session_file_idempotent(tmp_path):
    """Session file should be idempotent (calling twice with same args returns same path)."""
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    sid = "idempotent_test"
    result1 = session_file(agentflow_dir, "state.json", sid=sid)
    result2 = session_file(agentflow_dir, "state.json", sid=sid)

    assert result1 == result2
    assert (agentflow_dir / "sessions" / sid).exists()

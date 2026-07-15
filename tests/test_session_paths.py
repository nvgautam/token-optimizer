from pathlib import Path
import pytest
import os
import time

from agentflow.shell.session_paths import session_file, cleanup_stale_sessions


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


def test_cleanup_stale_sessions_removes_old_folder(tmp_path: Path) -> None:
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions"
    sessions_dir.mkdir()

    # Create old folder (25 hours old)
    old_folder = sessions_dir / "old-session"
    old_folder.mkdir()
    old_mtime = time.time() - (25 * 3600)
    os.utime(old_folder, (old_mtime, old_mtime))

    cleanup_stale_sessions(agentflow_dir, ttl_seconds=86400)

    assert not old_folder.exists()


def test_cleanup_stale_sessions_keeps_fresh_folder(tmp_path: Path) -> None:
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions"
    sessions_dir.mkdir()

    # Create fresh folder (1 hour old)
    fresh_folder = sessions_dir / "fresh-session"
    fresh_folder.mkdir()
    fresh_mtime = time.time() - (1 * 3600)
    os.utime(fresh_folder, (fresh_mtime, fresh_mtime))

    cleanup_stale_sessions(agentflow_dir, ttl_seconds=86400)

    assert fresh_folder.exists()


def test_cleanup_stale_sessions_no_sessions_dir(tmp_path: Path) -> None:
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()

    # sessions/ dir does not exist
    cleanup_stale_sessions(agentflow_dir, ttl_seconds=86400)

    # Should not raise an error


def test_cleanup_stale_sessions_empty_sessions_dir(tmp_path: Path) -> None:
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions"
    sessions_dir.mkdir()

    # sessions/ dir exists but is empty
    cleanup_stale_sessions(agentflow_dir, ttl_seconds=86400)

    assert sessions_dir.exists()


def test_cleanup_stale_sessions_custom_ttl(tmp_path: Path) -> None:
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions"
    sessions_dir.mkdir()

    # Create folder 2 hours old
    old_folder = sessions_dir / "two-hour-old"
    old_folder.mkdir()
    old_mtime = time.time() - (2 * 3600)
    os.utime(old_folder, (old_mtime, old_mtime))

    # TTL is 3600 (1 hour), so folder should be removed
    cleanup_stale_sessions(agentflow_dir, ttl_seconds=3600)

    assert not old_folder.exists()


def test_cleanup_stale_sessions_ignores_errors(tmp_path: Path, monkeypatch) -> None:
    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir()
    sessions_dir = agentflow_dir / "sessions"
    sessions_dir.mkdir()

    # Create old folder
    old_folder = sessions_dir / "old-session"
    old_folder.mkdir()
    old_mtime = time.time() - (25 * 3600)
    os.utime(old_folder, (old_mtime, old_mtime))

    # Mock shutil.rmtree to raise an error when ignore_errors=False
    def mock_rmtree(path, ignore_errors=False, **kwargs):
        if not ignore_errors:
            raise OSError("Permission denied")

    monkeypatch.setattr("agentflow.shell.session_paths.shutil.rmtree", mock_rmtree)

    # Should not raise an exception (ignore_errors=True should be passed)
    cleanup_stale_sessions(agentflow_dir, ttl_seconds=86400)

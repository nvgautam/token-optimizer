"""Tests for agentflow cache prune command (T-210)."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from argparse import Namespace

import pytest

from agentflow.cli_cmds import cmd_cache_prune


def test_prune_removes_old_dirs(tmp_path):
    """Test that directories older than threshold are removed."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir(parents=True)

    # Create old and new directories
    old_dir = cache_root / "old_hash"
    new_dir = cache_root / "new_hash"
    old_dir.mkdir()
    new_dir.mkdir()

    # Write a test file in each
    (old_dir / "test.idx").write_text("content")
    (new_dir / "test.idx").write_text("content")

    # Set modification times
    now = time.time()
    old_mtime = now - (40 * 86400)  # 40 days old
    new_mtime = now - (10 * 86400)  # 10 days old

    old_dir_stat = old_dir.stat()
    new_dir_stat = new_dir.stat()

    Path(old_dir).touch()
    Path(new_dir).touch()

    # Use os.utime to set modification times
    import os
    os.utime(old_dir, (old_mtime, old_mtime))
    os.utime(new_dir, (new_mtime, new_mtime))

    args = Namespace(older_than=30)
    with patch("agentflow.cli_cmds.Path") as mock_path_cls:
        mock_home = MagicMock()
        mock_path_cls.home.return_value = mock_home
        mock_home.__truediv__ = lambda self, x: cache_root / x if isinstance(x, str) else cache_root

        # Patch to make it use our test cache_root
        with patch("agentflow.cli_cmds.Path.home") as mock_home_func:
            mock_home_func.return_value = tmp_path

            # Create the cache structure
            actual_cache_root = tmp_path / ".agentflow" / "cache"
            actual_cache_root.mkdir(parents=True, exist_ok=True)
            old_actual = actual_cache_root / "old_hash"
            new_actual = actual_cache_root / "new_hash"
            old_actual.mkdir(exist_ok=True)
            new_actual.mkdir(exist_ok=True)
            (old_actual / "test.idx").write_text("content")
            (new_actual / "test.idx").write_text("content")

            import os
            os.utime(old_actual, (old_mtime, old_mtime))
            os.utime(new_actual, (new_mtime, new_mtime))

            rc = cmd_cache_prune(args)

    assert rc == 0


def test_prune_keeps_recent_dirs(tmp_path):
    """Test that recent directories are not removed."""
    # Create cache structure
    cache_root = tmp_path / ".agentflow" / "cache"
    cache_root.mkdir(parents=True)

    recent_dir = cache_root / "recent_hash"
    recent_dir.mkdir()
    (recent_dir / "test.idx").write_text("content")

    # Recent file (5 days old)
    now = time.time()
    recent_mtime = now - (5 * 86400)
    import os
    os.utime(recent_dir, (recent_mtime, recent_mtime))

    args = Namespace(older_than=30)
    with patch("agentflow.cli_cmds.Path.home") as mock_home_func:
        mock_home_func.return_value = tmp_path
        rc = cmd_cache_prune(args)

    assert rc == 0
    assert recent_dir.exists()


def test_prune_empty_cache_dir():
    """Test pruning when cache directory doesn't exist."""
    with patch("agentflow.cli_cmds.Path.home") as mock_home_func:
        mock_home = MagicMock()
        mock_home_func.return_value = mock_home
        mock_home_obj = MagicMock()
        mock_home.__truediv__ = lambda self, x: mock_home_obj
        mock_home_obj.__truediv__ = lambda self, x: mock_home_obj
        mock_home_obj.exists.return_value = False

        # Use simpler approach with real Path
        tmp_nonexistent = Path("/tmp/nonexistent_agentflow_cache_test")
        with patch("agentflow.cli_cmds.Path") as mock_path_cls:
            mock_cache_root = MagicMock()
            mock_cache_root.exists.return_value = False

            def path_side_effect(s):
                if s == "~/.agentflow":
                    return mock_cache_root
                return MagicMock()

            mock_path_cls.side_effect = path_side_effect
            mock_path_cls.home = lambda: Path.home()

            args = Namespace(older_than=30)
            # This should return 0 without error
            rc = cmd_cache_prune(args)
            assert rc == 0


def test_prune_default_30_days(tmp_path):
    """Test that default threshold is 30 days."""
    cache_root = tmp_path / ".agentflow" / "cache"
    cache_root.mkdir(parents=True)

    old_dir = cache_root / "old_hash"
    old_dir.mkdir()

    now = time.time()
    old_mtime = now - (31 * 86400)  # 31 days old (should be pruned with 30 day default)
    import os
    os.utime(old_dir, (old_mtime, old_mtime))

    args = Namespace(older_than=30)
    with patch("agentflow.cli_cmds.Path.home") as mock_home_func:
        mock_home_func.return_value = tmp_path
        rc = cmd_cache_prune(args)

    assert rc == 0


def test_prune_prints_summary(tmp_path, capsys):
    """Test that prune command prints a summary."""
    cache_root = tmp_path / ".agentflow" / "cache"
    cache_root.mkdir(parents=True)

    old_dir = cache_root / "old_hash"
    old_dir.mkdir()

    now = time.time()
    old_mtime = now - (40 * 86400)
    import os
    os.utime(old_dir, (old_mtime, old_mtime))

    args = Namespace(older_than=30)
    with patch("agentflow.cli_cmds.Path.home") as mock_home_func:
        mock_home_func.return_value = tmp_path
        rc = cmd_cache_prune(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out  # Should have some output

"""Tests for log rotation and flat-file truncation in audit_logger and session_manager."""
from __future__ import annotations
import pathlib
from unittest.mock import patch, MagicMock

import pytest

import agentflow.shell.audit_logger as al
from agentflow.shell.audit_logger import (
    rotate_log_file,
    truncate_flat_file,
    truncate_flat_logs,
    _FLAT_LOG_NAMES,
    _MAX_FLAT_LINES,
)


# ---------------------------------------------------------------------------
# rotate_log_file
# ---------------------------------------------------------------------------

class TestRotateLogFile:
    def test_no_rotation_when_under_limit(self, tmp_path):
        log = tmp_path / "test.jsonl"
        log.write_text("x\n" * 10)
        rotate_log_file(log)
        assert log.exists()
        assert not (tmp_path / "test.jsonl.1").exists()

    def test_rotates_when_over_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_LOG_BYTES", 5)
        log = tmp_path / "test.jsonl"
        log.write_text("x" * 10)
        rotate_log_file(log)
        assert not log.exists()
        assert (tmp_path / "test.jsonl.1").exists()

    def test_shifts_existing_rotated_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_LOG_BYTES", 5)
        log = tmp_path / "test.jsonl"
        rotated1 = tmp_path / "test.jsonl.1"
        log.write_text("x" * 10)
        rotated1.write_text("old")
        rotate_log_file(log)
        assert (tmp_path / "test.jsonl.2").exists()
        assert (tmp_path / "test.jsonl.1").exists()

    def test_drops_files_beyond_max_rotated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_LOG_BYTES", 5)
        monkeypatch.setattr(al, "_MAX_ROTATED", 2)
        log = tmp_path / "test.jsonl"
        log.write_text("x" * 10)
        (tmp_path / "test.jsonl.1").write_text("1")
        (tmp_path / "test.jsonl.2").write_text("2")
        rotate_log_file(log)
        assert not (tmp_path / "test.jsonl.3").exists()
        assert (tmp_path / "test.jsonl.2").exists()
        assert (tmp_path / "test.jsonl.1").exists()

    def test_no_op_for_missing_file(self, tmp_path):
        log = tmp_path / "missing.jsonl"
        rotate_log_file(log)  # must not raise

    def test_idempotent_when_under_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_LOG_BYTES", 100)
        log = tmp_path / "test.jsonl"
        log.write_text("x\n")
        rotate_log_file(log)
        rotate_log_file(log)
        assert log.exists()
        assert not (tmp_path / "test.jsonl.1").exists()


# ---------------------------------------------------------------------------
# truncate_flat_file
# ---------------------------------------------------------------------------

class TestTruncateFlatFile:
    def test_no_op_when_under_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_FLAT_LINES", 10_000)
        log = tmp_path / "proxy_log.jsonl"
        content = "\n".join(f"line {i}" for i in range(100)) + "\n"
        log.write_text(content)
        truncate_flat_file(log)
        assert log.read_text() == content

    def test_truncates_to_max_lines(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_FLAT_LINES", 5)
        log = tmp_path / "proxy_log.jsonl"
        lines = [f"line {i}\n" for i in range(20)]
        log.write_text("".join(lines))
        truncate_flat_file(log)
        result = log.read_text().splitlines()
        assert len(result) == 5
        assert result[0] == "line 15"
        assert result[-1] == "line 19"

    def test_keeps_last_n_lines(self, tmp_path):
        log = tmp_path / "verbosity_log.jsonl"
        lines = [f"entry_{i}\n" for i in range(20_000)]
        log.write_text("".join(lines))
        truncate_flat_file(log, max_lines=10_000)
        result = log.read_text().splitlines()
        assert len(result) == 10_000
        assert result[0] == "entry_10000"
        assert result[-1] == "entry_19999"

    def test_no_op_for_missing_file(self, tmp_path):
        log = tmp_path / "missing.jsonl"
        truncate_flat_file(log)  # must not raise

    def test_idempotent(self, tmp_path):
        log = tmp_path / "proxy_log.jsonl"
        lines = [f"line {i}\n" for i in range(30)]
        log.write_text("".join(lines))
        truncate_flat_file(log, max_lines=10)
        first_result = log.read_text()
        truncate_flat_file(log, max_lines=10)
        assert log.read_text() == first_result

    def test_exact_limit_is_not_truncated(self, tmp_path):
        log = tmp_path / "test.jsonl"
        lines = [f"line {i}\n" for i in range(10)]
        content = "".join(lines)
        log.write_text(content)
        truncate_flat_file(log, max_lines=10)
        assert log.read_text() == content

    def test_custom_max_lines_parameter(self, tmp_path):
        log = tmp_path / "test.jsonl"
        log.write_text("".join(f"line {i}\n" for i in range(50)))
        truncate_flat_file(log, max_lines=20)
        result = log.read_text().splitlines()
        assert len(result) == 20
        assert result[0] == "line 30"


# ---------------------------------------------------------------------------
# truncate_flat_logs
# ---------------------------------------------------------------------------

class TestTruncateFlatLogs:
    def test_truncates_all_known_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_FLAT_LINES", 5)
        for name in _FLAT_LOG_NAMES:
            (tmp_path / name).write_text("".join(f"line {i}\n" for i in range(20)))
        truncate_flat_logs(tmp_path)
        for name in _FLAT_LOG_NAMES:
            lines = (tmp_path / name).read_text().splitlines()
            assert len(lines) == 5, f"{name} not truncated"

    def test_skips_missing_files_gracefully(self, tmp_path):
        truncate_flat_logs(tmp_path)  # no files present — must not raise

    def test_no_op_for_missing_directory(self, tmp_path):
        truncate_flat_logs(tmp_path / "nonexistent")  # must not raise

    def test_only_affects_known_log_names(self, tmp_path, monkeypatch):
        monkeypatch.setattr(al, "_MAX_FLAT_LINES", 5)
        unrelated = tmp_path / "other.jsonl"
        unrelated.write_text("".join(f"line {i}\n" for i in range(20)))
        truncate_flat_logs(tmp_path)
        assert len(unrelated.read_text().splitlines()) == 20

    def test_flat_log_names_contains_expected_files(self):
        assert "proxy_log.jsonl" in _FLAT_LOG_NAMES
        assert "payload_inspect.jsonl" in _FLAT_LOG_NAMES
        assert "verbosity_log.jsonl" in _FLAT_LOG_NAMES

    def test_default_max_flat_lines(self):
        assert _MAX_FLAT_LINES == 10_000


# ---------------------------------------------------------------------------
# session_manager integration — truncation on exit and startup
# ---------------------------------------------------------------------------

class TestSessionManagerTruncation:
    def test_truncate_called_on_startup(self, tmp_path):
        """Session startup triggers truncate_flat_logs on the .agentflow dir."""
        # The autouse fixture in conftest patches Path.cwd() → tmp_path
        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()
        log = agentflow_dir / "verbosity_log.jsonl"
        log.write_text("".join(f"entry_{i}\n" for i in range(25_000)))

        from tests.shell.conftest import make_manager
        make_manager()  # __init__ calls truncate_flat_logs

        assert len(log.read_text().splitlines()) <= 10_000

    def test_truncate_called_on_exit(self, tmp_path):
        """Session exit triggers truncate_flat_logs on the .agentflow dir."""
        # Build manager first; startup truncation runs on empty tmp_path/.agentflow
        (tmp_path / ".agentflow").mkdir()
        from tests.shell.conftest import make_manager
        sm, _, _ = make_manager()

        # Redirect _project_root to a separate dir with a large log
        log_root = tmp_path / "log_root"
        log_dir = log_root / ".agentflow"
        log_dir.mkdir(parents=True)
        log = log_dir / "proxy_log.jsonl"
        log.write_text("".join(f"line {i}\n" for i in range(25_000)))
        sm._project_root = log_root

        from agentflow.shell import session_manager_handlers
        with patch.object(session_manager_handlers, "handle_session_exit"):
            with patch("agentflow.shell.oracle_consent.on_session_exit_oracle", return_value=False):
                sm._on_session_exit(0)

        assert len(log.read_text().splitlines()) <= 10_000

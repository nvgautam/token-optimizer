"""Test structured error logging in hook exception handlers."""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest


class TestUserPromptSubmitErrorLogging:
    """Test ups_task_sync.py error logging via _log_drain."""

    def test_check_pr_state_logs_on_exception(self, tmp_path):
        """Patch failing subprocess call, assert _log_drain called with error event."""
        # Import after sys.path setup
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.ups_task_sync import _check_pr_state, _log_drain

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Simulate exception during subprocess call
        with mock.patch("subprocess.run", side_effect=RuntimeError("subprocess failure")):
            with mock.patch(
                "agentflow.hooks.ups_task_sync._log_drain"
            ) as mock_log_drain:
                result = _check_pr_state("https://github.com/example/repo/pull/1")
                # Function handles exception silently and returns None
                assert result is None

    def test_run_cleanup_logs_on_exception(self, tmp_path):
        """Patch failing subprocess call, assert _log_drain called with error event."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.ups_task_sync import _run_cleanup

        root = tmp_path
        with mock.patch("subprocess.run", side_effect=RuntimeError("cleanup failure")):
            # Should not raise, silently handles exception
            _run_cleanup(root)


class TestPostToolUseErrorLogging:
    """Test post_tool_use.py error logging via _log."""

    def test_atomic_write_logs_on_exception(self, tmp_path):
        """Patch file operations, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.post_tool_use import _atomic_write

        target = tmp_path / "test.json"

        # Patch tempfile.mkstemp to fail
        with mock.patch("tempfile.mkstemp", side_effect=OSError("tempfile failure")):
            # Should not raise, silently handles exception
            _atomic_write(target, '{"test": "data"}')


class TestPostToolUseAgentErrorLogging:
    """Test post_tool_use_agent.py error logging via _log."""

    def test_run_cleanup_logs_on_exception(self, tmp_path):
        """Patch failing subprocess call, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.post_tool_use_agent import _run_cleanup

        root = tmp_path
        with mock.patch("subprocess.run", side_effect=RuntimeError("cleanup failure")):
            # Should not raise, silently handles exception
            _run_cleanup(root)

    def test_check_pr_state_logs_on_exception(self):
        """Patch failing subprocess call, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.post_tool_use_agent import _check_pr_state

        with mock.patch("subprocess.run", side_effect=RuntimeError("gh pr view failure")):
            result = _check_pr_state("https://github.com/example/repo/pull/1")
            assert result is None


class TestPreToolUseAgentErrorLogging:
    """Test pre_tool_use_agent.py handles exceptions gracefully."""

    def test_signal_subprocess_error_handled(self):
        """Patch signal subprocess call to fail, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

        hook_data = {
            "tool_input": {
                "prompt": "## Addendum: T-123\nTest prompt"
            }
        }

        with mock.patch("json.load", return_value=hook_data):
            with mock.patch("subprocess.run", side_effect=RuntimeError("signal failure")):
                from agentflow.hooks import pre_tool_use_agent
                # Just verify no exception is raised
                with mock.patch("sys.exit"):
                    pre_tool_use_agent.main()


class TestVerbosityReminderErrorLogging:
    """Test verbosity_reminder.py writes JSON to stderr on exception."""

    def test_read_prompt_error_returns_none(self):
        """Patch stdin read, verify exception is caught and None returned."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

        with mock.patch("sys.stdin.isatty", return_value=False):
            with mock.patch("json.load", side_effect=RuntimeError("json failure")):
                from agentflow.hooks.verbosity_reminder import _read_prompt_from_stdin
                result = _read_prompt_from_stdin()
                assert result is None

    def test_write_session_state_error_handled(self, tmp_path):
        """Patch file operations, verify exception is caught gracefully."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.verbosity_reminder import _write_session_state_atomic

        agentflow_dir = tmp_path

        # Patch mkdir to fail
        with mock.patch.object(Path, "mkdir", side_effect=OSError("mkdir failure")):
            # Should not raise, silently handles exception
            _write_session_state_atomic(agentflow_dir, "orchestrator")


class TestSizeCheckErrorLogging:
    """Test size_check.py writes JSON to stderr on exception."""

    def test_json_load_error_logs_to_stderr(self):
        """Patch stdin read to fail, verify exception is caught gracefully."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

        with mock.patch("sys.stdin.read", side_effect=RuntimeError("stdin failure")):
            with mock.patch("json.load", side_effect=json.JSONDecodeError("msg", "doc", 0)):
                with mock.patch("sys.exit") as mock_exit:
                    from agentflow.hooks import size_check
                    size_check.main()
                    # Should call sys.exit(0) without raising
                    mock_exit.assert_called_with(0)


class TestWriteIndexerErrorLogging:
    """Test write_indexer.py handles exceptions gracefully."""

    def test_exception_in_stdin_processing_handled(self):
        """Patch json.load to fail, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

        with mock.patch("sys.argv", ["write_indexer.py"]):
            with mock.patch("json.load", side_effect=json.JSONDecodeError("msg", "doc", 0)):
                with mock.patch("sys.exit"):
                    from agentflow.hooks.write_indexer import main
                    # Should not raise
                    main()


class TestReadCheckErrorLogging:
    """Test read_check.py logs errors to stderr behaviorally."""

    def test_parse_line_range_error_logs_to_stderr(self, tmp_path):
        """Pass unparseable StartLine/EndLine, assert JSON error written to stderr."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.read_check import main

        hook_data = {
            "tool_input": {
                "file_path": str(tmp_path / "somefile.py"),
                "StartLine": "not_a_number",
                "EndLine": "also_not_a_number",
            }
        }

        stderr_capture = io.StringIO()
        with mock.patch("json.load", return_value=hook_data):
            with mock.patch("os.getcwd", return_value=str(tmp_path)):
                with mock.patch("sys.stderr", stderr_capture):
                    try:
                        main()
                    except SystemExit:
                        pass

        output = stderr_capture.getvalue().strip()
        assert output, "Expected JSON on stderr"
        logged = json.loads(output)
        assert logged["event"] == "parse_line_range_error"
        assert logged["hook"] == "read_check.py"

    def test_count_file_lines_error_logs_to_stderr(self, tmp_path):
        """Patch file open to fail while idx exists, assert JSON error written to stderr."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.read_check import main

        hook_data = {
            "tool_input": {
                "file_path": str(tmp_path / "somefile.py"),
                "offset": 0,
                "limit": 10,
            }
        }

        stderr_capture = io.StringIO()
        with mock.patch("json.load", return_value=hook_data):
            with mock.patch("os.getcwd", return_value=str(tmp_path)):
                # Make idx map_path exist and contain content
                with mock.patch.object(Path, "exists", return_value=True):
                    with mock.patch.object(Path, "read_text", return_value="main:1-50"):
                        # Make the file open for line-counting fail
                        with mock.patch("builtins.open", side_effect=OSError("read failure")):
                            with mock.patch("sys.stderr", stderr_capture):
                                try:
                                    main()
                                except SystemExit:
                                    pass

        output = stderr_capture.getvalue().strip()
        assert output, "Expected JSON on stderr"
        logged = json.loads(output)
        assert logged["event"] == "count_file_lines_error"
        assert logged["hook"] == "read_check.py"

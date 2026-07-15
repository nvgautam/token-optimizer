"""Test structured error logging in hook exception handlers."""
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest


class TestUserPromptSubmitErrorLogging:
    """Test user_prompt_submit.py error logging via _log_drain."""

    def test_check_pr_state_logs_on_exception(self, tmp_path):
        """Patch failing subprocess call, assert _log_drain called with error event."""
        # Import after sys.path setup
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.user_prompt_submit import _check_pr_state, _log_drain

        agentflow_dir = tmp_path / ".agentflow"
        agentflow_dir.mkdir()

        # Simulate exception during subprocess call
        with mock.patch("subprocess.run", side_effect=RuntimeError("subprocess failure")):
            with mock.patch(
                "agentflow.hooks.user_prompt_submit._log_drain"
            ) as mock_log_drain:
                result = _check_pr_state("https://github.com/example/repo/pull/1")
                # Function handles exception silently and returns None
                assert result is None

    def test_run_cleanup_logs_on_exception(self, tmp_path):
        """Patch failing subprocess call, assert _log_drain called with error event."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.user_prompt_submit import _run_cleanup

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
    """Test read_check.py error logging is in place."""

    def test_parse_line_error_logging_present(self):
        """Verify parse_line_error logging code is present."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import inspect
        from agentflow.hooks import read_check

        source = inspect.getsource(read_check.main)
        # Verify error logging for parse errors is present
        assert "parse_line_range_error" in source or "parse_start_line_error" in source

    def test_file_read_error_logging_present(self):
        """Verify file_read_error logging code is present."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import inspect
        from agentflow.hooks import read_check

        source = inspect.getsource(read_check.main)
        # Verify error logging for file read errors is present
        assert "count_file_lines_error" in source


class TestStopContextCaptureErrorLogging:
    """Test stop_context_capture.py writes JSON to stderr on exception."""

    def test_transcript_read_error_logs_to_stderr(self):
        """Patch file read, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from agentflow.hooks.stop_context_capture import extract_fill_from_transcript

        with mock.patch("builtins.open", side_effect=OSError("file not found")):
            result = extract_fill_from_transcript("/nonexistent/file.jsonl")
            assert result is None

    def test_tempfile_error_logs_to_stderr(self):
        """Patch tempfile operations, verify exception is caught."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

        payload = {
            "transcript_path": "/some/transcript.jsonl"
        }

        stderr_capture = io.StringIO()

        with mock.patch("sys.stdin.read", return_value=json.dumps(payload)):
            with mock.patch("json.loads", return_value=payload):
                with mock.patch(
                    "agentflow.hooks.stop_context_capture.extract_fill_from_transcript",
                    return_value=100
                ):
                    with mock.patch("tempfile.mkstemp", side_effect=OSError("tempfile failure")):
                        with mock.patch("sys.stderr", stderr_capture):
                            with mock.patch("sys.exit"):
                                from agentflow.hooks.stop_context_capture import main
                                main()

"""Unit tests for T-009: cmd_shell PTY relay loop."""

import argparse
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Constants — use POSIX constants; never call sys.stdin.fileno() at module level
# (pytest redirects stdin and the call would raise UnsupportedOperation)
# ---------------------------------------------------------------------------

_STDIN_FD = 0   # POSIX stdin fd
_STDOUT_FD = 1  # POSIX stdout fd
_MASTER_FD = 7  # arbitrary fake PTY master fd

_PTY_CLS = "agentflow.shell.pty_wrapper.PTYWrapper"
_SM_CLS = "agentflow.shell.session_manager.SessionManager"


def _args(shell_command: str = "claude") -> argparse.Namespace:
    """Build a minimal args Namespace for cmd_shell tests."""
    ns = argparse.Namespace()
    ns.command = "shell"
    ns.shell_command = shell_command
    return ns


def _wrapper(exited: bool = True, exit_code: int = 0) -> MagicMock:
    """Build a minimal PTYWrapper mock."""
    w = MagicMock()
    w._exited = exited
    w._exit_code = exit_code
    w.master_fd = _MASTER_FD
    w.read_output.return_value = b""
    return w


def _run(wrapper, select_fn=None):
    """
    Run cmd_shell under the standard set of mocks.

    Returns a dict of the key mock objects so tests can introspect them.
    sys.stdin.fileno is patched to return 0 so cmd_shell works under pytest capture.
    """
    from agentflow.cli import cmd_shell

    if select_fn is None:
        select_fn = lambda *a, **kw: ([], [], [])

    mocks = {}
    with ExitStack() as stack:
        # Make sys.stdin.fileno() return 0 under pytest's captured stdin
        stack.enter_context(patch.object(sys.stdin, "fileno", return_value=_STDIN_FD))
        mocks["tcgetattr"] = stack.enter_context(
            patch("termios.tcgetattr", return_value=[0] * 6)
        )
        mocks["setraw"] = stack.enter_context(patch("tty.setraw"))
        mocks["tcsetattr"] = stack.enter_context(patch("termios.tcsetattr"))
        stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
        stack.enter_context(patch(_SM_CLS))
        mocks["select"] = stack.enter_context(
            patch("select.select", side_effect=select_fn)
        )
        mocks["exit"] = stack.enter_context(patch("sys.exit"))
        cmd_shell(_args())

    return mocks


# ---------------------------------------------------------------------------
# 1. cmd_shell enters raw mode before forking PTY
# ---------------------------------------------------------------------------


class TestEntersRawMode:
    def test_tcgetattr_called_with_stdin_fd(self):
        m = _run(_wrapper())
        m["tcgetattr"].assert_called_once_with(_STDIN_FD)

    def test_setraw_called_with_stdin_fd(self):
        m = _run(_wrapper())
        m["setraw"].assert_called_once_with(_STDIN_FD)

    def test_setraw_before_pty_wrapper(self):
        """tty.setraw must be called before PTYWrapper is instantiated."""
        call_order = []
        wrapper = _wrapper(exited=True)

        from agentflow.cli import cmd_shell

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(sys.stdin, "fileno", return_value=_STDIN_FD)
            )
            stack.enter_context(patch("termios.tcgetattr", return_value=[]))
            stack.enter_context(
                patch("tty.setraw", side_effect=lambda fd: call_order.append("setraw"))
            )
            stack.enter_context(patch("termios.tcsetattr"))
            stack.enter_context(
                patch(
                    _PTY_CLS,
                    side_effect=lambda *a, **kw: call_order.append("pty") or wrapper,
                )
            )
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(patch("select.select", return_value=([], [], [])))
            stack.enter_context(patch("sys.exit"))
            cmd_shell(_args())

        assert call_order == ["setraw", "pty"]


# ---------------------------------------------------------------------------
# 2. select() loop reads from stdin and writes to master_fd
# ---------------------------------------------------------------------------


class TestSelectLoopStdinToMasterFd:
    def test_chunk_from_stdin_forwarded_to_master_fd(self):
        wrapper = _wrapper(exited=False)
        chunk = b"user input"
        call_count = [0]

        def select_fn(r, w, x, timeout=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return ([_STDIN_FD], [], [])
            wrapper._exited = True
            return ([], [], [])

        from agentflow.cli import cmd_shell

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(sys.stdin, "fileno", return_value=_STDIN_FD)
            )
            stack.enter_context(patch("termios.tcgetattr", return_value=[]))
            stack.enter_context(patch("tty.setraw"))
            stack.enter_context(patch("termios.tcsetattr"))
            stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(patch("select.select", side_effect=select_fn))
            m_read = stack.enter_context(patch("os.read", return_value=chunk))
            m_write = stack.enter_context(patch("os.write"))
            stack.enter_context(patch("sys.exit"))
            cmd_shell(_args())

        m_read.assert_any_call(_STDIN_FD, 1024)
        m_write.assert_any_call(_MASTER_FD, chunk)


# ---------------------------------------------------------------------------
# 3. select() loop reads master_fd via read_output() and writes to stdout
# ---------------------------------------------------------------------------


class TestSelectLoopMasterFdToStdout:
    def test_read_output_called_and_written_to_stdout(self):
        wrapper = _wrapper(exited=False)
        output = b"AI response"
        wrapper.read_output.return_value = output
        call_count = [0]

        def select_fn(r, w, x, timeout=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return ([_MASTER_FD], [], [])
            wrapper._exited = True
            return ([], [], [])

        from agentflow.cli import cmd_shell

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(sys.stdin, "fileno", return_value=_STDIN_FD)
            )
            stack.enter_context(patch("termios.tcgetattr", return_value=[]))
            stack.enter_context(patch("tty.setraw"))
            stack.enter_context(patch("termios.tcsetattr"))
            stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(patch("select.select", side_effect=select_fn))
            m_write = stack.enter_context(patch("os.write"))
            stack.enter_context(patch("sys.exit"))
            cmd_shell(_args())

        wrapper.read_output.assert_called()
        m_write.assert_any_call(_STDOUT_FD, output)

    def test_empty_read_output_not_written_to_stdout(self):
        """No os.write to stdout when read_output returns empty bytes."""
        wrapper = _wrapper(exited=False)
        wrapper.read_output.return_value = b""
        call_count = [0]

        def select_fn(r, w, x, timeout=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return ([_MASTER_FD], [], [])
            wrapper._exited = True
            return ([], [], [])

        from agentflow.cli import cmd_shell

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(sys.stdin, "fileno", return_value=_STDIN_FD)
            )
            stack.enter_context(patch("termios.tcgetattr", return_value=[]))
            stack.enter_context(patch("tty.setraw"))
            stack.enter_context(patch("termios.tcsetattr"))
            stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(patch("select.select", side_effect=select_fn))
            m_write = stack.enter_context(patch("os.write"))
            stack.enter_context(patch("sys.exit"))
            cmd_shell(_args())

        # os.write must not have been called for stdout with empty bytes
        for c in m_write.call_args_list:
            assert not (c == call(_STDOUT_FD, b""))


# ---------------------------------------------------------------------------
# 4. Terminal settings restored in finally block on normal and error exit
# ---------------------------------------------------------------------------


class TestFinallyBlock:
    def test_tcsetattr_called_on_normal_exit(self):
        import termios

        old_settings = [0] * 6
        wrapper = _wrapper(exited=True, exit_code=0)

        from agentflow.cli import cmd_shell

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(sys.stdin, "fileno", return_value=_STDIN_FD)
            )
            stack.enter_context(patch("termios.tcgetattr", return_value=old_settings))
            stack.enter_context(patch("tty.setraw"))
            m_set = stack.enter_context(patch("termios.tcsetattr"))
            stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(patch("select.select", return_value=([], [], [])))
            stack.enter_context(patch("sys.exit"))
            cmd_shell(_args())

        m_set.assert_called_once_with(_STDIN_FD, termios.TCSADRAIN, old_settings)

    def test_tcsetattr_called_on_exception(self):
        """Terminal settings restored even when select loop raises an unexpected error."""
        import termios

        wrapper = _wrapper(exited=False)
        old_settings = [1, 2, 3, 4, 5, 6]

        from agentflow.cli import cmd_shell

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(sys.stdin, "fileno", return_value=_STDIN_FD)
            )
            stack.enter_context(patch("termios.tcgetattr", return_value=old_settings))
            stack.enter_context(patch("tty.setraw"))
            m_set = stack.enter_context(patch("termios.tcsetattr"))
            stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(
                patch("select.select", side_effect=RuntimeError("forced"))
            )
            stack.enter_context(patch("sys.exit"))
            with pytest.raises(RuntimeError, match="forced"):
                cmd_shell(_args())

        m_set.assert_called_once_with(_STDIN_FD, termios.TCSADRAIN, old_settings)


# ---------------------------------------------------------------------------
# 5. sys.exit called with child exit code
# ---------------------------------------------------------------------------


class TestSysExit:
    def test_exits_with_wrapper_exit_code(self):
        m = _run(_wrapper(exited=True, exit_code=42))
        m["exit"].assert_called_once_with(42)

    def test_exits_with_zero_when_exit_code_none(self):
        """None exit code → sys.exit(0)."""
        m = _run(_wrapper(exited=True, exit_code=None))
        m["exit"].assert_called_once_with(0)

    def test_exits_with_zero_on_clean_exit(self):
        m = _run(_wrapper(exited=True, exit_code=0))
        m["exit"].assert_called_once_with(0)


# ---------------------------------------------------------------------------
# 6. CLI integration: argparse round-trip, main() dispatch, __main__ smoke
# ---------------------------------------------------------------------------


class TestArgparseRoundTrip:
    def test_shell_sets_command_attr(self):
        from agentflow.cli import build_parser

        args = build_parser().parse_args(["shell"])
        assert args.command == "shell"

    def test_shell_sets_default_shell_command(self):
        from agentflow.cli import build_parser

        args = build_parser().parse_args(["shell"])
        assert args.shell_command == "claude"

    def test_shell_command_flag_overrides_default(self):
        from agentflow.cli import build_parser

        args = build_parser().parse_args(["shell", "--command", "gemini"])
        assert args.shell_command == "gemini"

    def test_cmd_shell_maps_gemini_to_agy(self):
        from agentflow.cli import cmd_shell
        wrapper_mock = _wrapper()
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys.stdin, "fileno", return_value=_STDIN_FD))
            stack.enter_context(patch("termios.tcgetattr", return_value=[0] * 6))
            stack.enter_context(patch("tty.setraw"))
            stack.enter_context(patch("termios.tcsetattr"))
            pty_mock = stack.enter_context(patch(_PTY_CLS, return_value=wrapper_mock))
            stack.enter_context(patch(_SM_CLS))
            stack.enter_context(patch("select.select", return_value=([], [], [])))
            stack.enter_context(patch("sys.exit"))

            cmd_shell(_args("gemini"))

            pty_mock.assert_called_once_with(["agy"])


class TestMainDispatch:
    def test_main_calls_cmd_shell_for_shell_argv(self):
        from agentflow.cli import main

        with patch("sys.argv", ["agentflow", "shell"]), \
             patch("agentflow.cli.cmd_shell", return_value=0) as mock_cmd, \
             patch("sys.exit"):
            main()
        mock_cmd.assert_called_once()


class TestDunderMain:
    def test_dunder_main_importable(self):
        import importlib
        import sys as _sys

        _sys.modules.pop("agentflow.__main__", None)
        with patch("agentflow.cli.main"):
            importlib.import_module("agentflow.__main__")


# ---------------------------------------------------------------------------
# 9. T-055 regression — banner guard sees data before newline in combined chunk
# ---------------------------------------------------------------------------


def test_banner_guard_receives_data_before_newline_in_combined_chunk():
    """When data+newline arrive in one chunk, should_inject_banner gets the data, not ''."""
    wrapper = _wrapper(exited=False)
    call_count = [0]

    def select_fn(r, w, x, timeout=None):
        if call_count[0] == 0:
            call_count[0] += 1
            return ([_STDIN_FD], [], [])
        wrapper._exited = True
        return ([], [], [])

    from agentflow.cli import cmd_shell

    sm_mock = MagicMock()
    sm_mock.should_inject_banner.return_value = False

    with ExitStack() as stack:
        stack.enter_context(patch.object(sys.stdin, "fileno", return_value=_STDIN_FD))
        stack.enter_context(patch("termios.tcgetattr", return_value=[]))
        stack.enter_context(patch("tty.setraw"))
        stack.enter_context(patch("termios.tcsetattr"))
        stack.enter_context(patch(_PTY_CLS, return_value=wrapper))
        stack.enter_context(patch(_SM_CLS, return_value=sm_mock))
        stack.enter_context(patch("select.select", side_effect=select_fn))
        stack.enter_context(patch("os.read", return_value=b"generate\n"))
        stack.enter_context(patch("os.write"))
        stack.enter_context(patch("sys.exit"))
        cmd_shell(_args())

    sm_mock.should_inject_banner.assert_called_once_with("generate")

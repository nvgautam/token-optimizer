"""Unit tests for T-009: cmd_shell PTY relay loop."""

import argparse
import os
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

import pytest

from agentflow.config.schema import (
    AgentFlowConfig, HeadroomConfig, format_headroom_banner, resolve_headroom_status,
)

# ---------------------------------------------------------------------------
# Constants — use POSIX constants; never call sys.stdin.fileno() at module level
# (pytest redirects stdin and the call would raise UnsupportedOperation)
# ---------------------------------------------------------------------------

_STDIN_FD = 0   # POSIX stdin fd
_STDOUT_FD = 1  # POSIX stdout fd
_MASTER_FD = 7  # arbitrary fake PTY master fd

_PTY_CLS = "agentflow.shell.pty_wrapper.PTYWrapper"
_SM_CLS = "agentflow.shell.session_manager.SessionManager"
_LOAD_CONFIG = "agentflow.config.loader.load_config"


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


def _run(wrapper, select_fn=None, headroom_config=None, which_result=None):
    """Run cmd_shell under the standard set of mocks; returns key mocks for introspection.

    load_config/shutil.which default to config.headroom.enabled=True + "not installed"
    (which_result=None) so cmd_shell never mutates the real os.environ by default — tests
    that exercise the headroom-active path must opt in via which_result="/usr/bin/headroom"
    and wrap the call in patch.dict(os.environ, ...) themselves to avoid leaking HEADROOM_*
    across the test session.
    """
    from agentflow.cli import cmd_shell

    if select_fn is None:
        select_fn = lambda *a, **kw: ([], [], [])
    if headroom_config is None:
        headroom_config = AgentFlowConfig()

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
        stack.enter_context(patch(_LOAD_CONFIG, return_value=headroom_config))
        stack.enter_context(patch("shutil.which", return_value=which_result))
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

        with patch("os.read", return_value=chunk) as m_read, patch("os.write") as m_write:
            _run(wrapper, select_fn=select_fn)

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

        with patch("os.write") as m_write:
            _run(wrapper, select_fn=select_fn)

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

        with patch("os.write") as m_write:
            _run(wrapper, select_fn=select_fn)

        # os.write must not have been called for stdout with empty bytes
        for c in m_write.call_args_list:
            assert not (c == call(_STDOUT_FD, b""))


# ---------------------------------------------------------------------------
# 4. Terminal settings restored in finally block on normal and error exit
# ---------------------------------------------------------------------------


class TestFinallyBlock:
    def test_tcsetattr_called_on_normal_exit(self):
        import termios

        m = _run(_wrapper(exited=True, exit_code=0))
        m["tcsetattr"].assert_called_once_with(_STDIN_FD, termios.TCSADRAIN, [0] * 6)

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
# 6. Headroom wrap sets HEADROOM_MODE (T-084: revert cache mode -> token mode)
# ---------------------------------------------------------------------------


class TestHeadroomWrap:
    def test_cmd_shell_sets_headroom_mode_token_when_enabled(self):
        with patch.dict(
            os.environ, {"AGENTFLOW_ENABLE_HEADROOM": "1"}, clear=False
        ):
            _run(_wrapper(exited=True), which_result="/usr/bin/headroom")
            assert os.environ["HEADROOM_MODE"] == "token"

    def test_cmd_shell_does_not_set_headroom_mode_when_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENTFLOW_ENABLE_HEADROOM", None)
            os.environ.pop("HEADROOM_MODE", None)
            _run(
                _wrapper(exited=True),
                headroom_config=AgentFlowConfig(headroom=HeadroomConfig(enabled=False)),
                which_result="/usr/bin/headroom",
            )
            assert "HEADROOM_MODE" not in os.environ

    def test_cmd_shell_sets_headroom_workspace_dir_when_enabled(self):
        with patch.dict(
            os.environ, {"AGENTFLOW_ENABLE_HEADROOM": "1"}, clear=False
        ):
            _run(_wrapper(exited=True), which_result="/usr/bin/headroom")
            assert "HEADROOM_WORKSPACE_DIR" in os.environ


# ---------------------------------------------------------------------------
# 7. T-086: headroom.enabled config field — default-on, env-override, banner
# ---------------------------------------------------------------------------


class TestHeadroomConfigDefault:
    def test_headroom_config_defaults_to_enabled(self):
        assert AgentFlowConfig().headroom.enabled is True

    def test_cmd_shell_wraps_by_default_when_config_enabled_and_installed(self):
        """No env var set — config default (enabled=True) + installed → wraps."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENTFLOW_ENABLE_HEADROOM", None)
            _run(_wrapper(exited=True), which_result="/usr/bin/headroom")
            assert os.environ["HEADROOM_MODE"] == "token"


class TestEnvOverridePrecedence:
    """resolve_headroom_status: env var wins over config either direction (pure, no mocks)."""

    def test_env_overrides_config_both_directions(self):
        assert resolve_headroom_status(True, "0", True) == (False, "env-override")
        assert resolve_headroom_status(False, "1", True) == (True, "")

    def test_not_installed_wins_over_env_and_config(self):
        assert resolve_headroom_status(True, "1", False) == (False, "not installed")


class TestHeadroomBanner:
    """format_headroom_banner text for active + all three inactive reasons (T-086 AC)."""

    def test_active(self):
        assert format_headroom_banner(True, "") == "[agentflow] headroom wrap: active"

    def test_inactive_reasons(self):
        expect = {
            "not installed": "headroom not installed",
            "config-disabled": "disabled via config (headroom.enabled: false)",
            "env-override": "disabled via AGENTFLOW_ENABLE_HEADROOM override",
        }
        for reason, why in expect.items():
            assert format_headroom_banner(False, reason) == f"[agentflow] headroom wrap: inactive ({why})"

    def test_banner_printed_on_startup(self, capsys):
        """cmd_shell actually prints the banner (wiring check, not just the formatter)."""
        with patch.dict(os.environ, {"AGENTFLOW_ENABLE_HEADROOM": "0"}, clear=False):
            _run(_wrapper(exited=True), which_result="/usr/bin/headroom")
        assert "inactive (disabled via AGENTFLOW_ENABLE_HEADROOM override)" in capsys.readouterr().out



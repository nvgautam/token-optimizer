"""Unit tests for cmd_shell dispatch, integration, and headroom wrapping (T-074)."""

import argparse
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

_STDIN_FD = 0
_MASTER_FD = 7
_PTY_CLS = "agentflow.shell.pty_wrapper.PTYWrapper"
_SM_CLS = "agentflow.shell.session_manager.SessionManager"


def _args(shell_command: str = "claude") -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.command = "shell"
    ns.shell_command = shell_command
    return ns


def _wrapper(exited: bool = True, exit_code: int = 0) -> MagicMock:
    w = MagicMock()
    w._exited = exited
    w._exit_code = exit_code
    w.master_fd = _MASTER_FD
    w.read_output.return_value = b""
    return w


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


_PROXY_CLS = "agentflow.shell.pty_shell.ProxyShell"


class TestProxyShellDispatch:
    """T-093: cmd_shell uses ProxyShell instead of headroom CLI wrap."""

    def _run_cmd_shell(self, shell_command: str, tmp_path, proxy_mock):
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
            stack.enter_context(patch("pathlib.Path.cwd", return_value=tmp_path))
            stack.enter_context(patch(_PROXY_CLS, return_value=proxy_mock))

            from agentflow.cli import cmd_shell
            cmd_shell(_args(shell_command))
            return pty_mock

    def test_proxy_start_called_before_pty(self, tmp_path):
        """ProxyShell.start() is called before entering raw mode."""
        proxy_mock = MagicMock()
        proxy_mock.banner.return_value = "[agentflow] proxy: active (http://127.0.0.1:9999)"
        self._run_cmd_shell("claude", tmp_path, proxy_mock)
        proxy_mock.start.assert_called_once()

    def test_proxy_stop_called_in_finally(self, tmp_path):
        """ProxyShell.stop() is called in finally block regardless of PTY exit."""
        proxy_mock = MagicMock()
        proxy_mock.banner.return_value = "[agentflow] proxy: inactive (headroom not available)"
        self._run_cmd_shell("claude", tmp_path, proxy_mock)
        proxy_mock.stop.assert_called_once()

    def test_pty_receives_bare_command(self, tmp_path):
        """PTYWrapper is called with just [cmd] — no headroom CLI wrapping."""
        proxy_mock = MagicMock()
        proxy_mock.banner.return_value = "[agentflow] proxy: active (http://127.0.0.1:9999)"
        pty_mock = self._run_cmd_shell("claude", tmp_path, proxy_mock)
        pty_mock.assert_called_once_with(["claude"])

    def test_no_headroom_env_vars_set(self, tmp_path):
        """HEADROOM_WORKSPACE_DIR and HEADROOM_MODE are never set by cmd_shell."""
        import os
        proxy_mock = MagicMock()
        proxy_mock.banner.return_value = "[agentflow] proxy: inactive (headroom not available)"
        self._run_cmd_shell("claude", tmp_path, proxy_mock)
        assert "HEADROOM_WORKSPACE_DIR" not in os.environ
        assert "HEADROOM_MODE" not in os.environ

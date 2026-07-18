"""Tests for T-243: spawn_new_child passes --auto to claude/claude2 orchestrator restarts."""
from __future__ import annotations

import pty as pty_module
import sys
import pathlib
from unittest.mock import patch

import pytest

from agentflow.shell.process_manager import spawn_new_child

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from conftest import make_manager


def _capture_exec(sm, initial_command: list[str]) -> list[str]:
    """Run spawn_new_child and return the args passed to os.execvp.

    pty.fork is mocked to return pid=0 (child side) so execvp is reached.
    os.execvp raises SystemExit(127) via side_effect so we can catch it and
    inspect what was captured.
    """
    sm._pty._command = initial_command
    exec_called: list[list[str]] = []

    with (
        patch.object(pty_module, "fork", return_value=(0, 123)),
        patch(
            "os.execvp",
            side_effect=lambda cmd, args: exec_called.append(list(args))
            or (_ for _ in ()).throw(SystemExit(127)),
        ),
        patch("os._exit"),
    ):
        try:
            spawn_new_child(sm)
        except SystemExit:
            pass

    assert exec_called, "os.execvp was never called"
    return exec_called[0]


class TestAutoFlag:
    """T-243: --auto appended for claude/claude2 orchestrator restarts only."""

    def test_orchestrator_claude_gets_auto(self):
        """orchestrator + claude → --auto in command."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["claude"])
        assert "--auto" in args, f"Expected --auto in {args}"

    def test_orchestrator_claude2_gets_auto(self):
        """orchestrator + claude2 → --auto in command."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["claude2"])
        assert "--auto" in args, f"Expected --auto in {args}"

    def test_orchestrator_agy_no_auto(self):
        """orchestrator + agy → no --auto."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["agy"])
        assert "--auto" not in args, f"Did not expect --auto in {args}"

    def test_oracle_claude_no_auto(self):
        """oracle + claude → no --auto."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "oracle"

        args = _capture_exec(sm, ["claude"])
        assert "--auto" not in args, f"Did not expect --auto in {args}"

    def test_first_launch_no_auto(self):
        """_just_restarted=False → no --auto even for orchestrator+claude."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = False
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["claude"])
        assert "--auto" not in args, f"Did not expect --auto in {args}"

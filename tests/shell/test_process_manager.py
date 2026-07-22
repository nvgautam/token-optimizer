"""Tests for T-243/T-329: spawn_new_child and _get_claude_skill_cmd."""
from __future__ import annotations

import pty as pty_module
import sys
import pathlib
from unittest.mock import patch


from agentflow.shell.process_manager import spawn_new_child, _get_claude_skill_cmd

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
    """T-243: --permission-mode auto appended for claude/claude2 orchestrator restarts only."""

    def test_orchestrator_claude_gets_auto(self):
        """orchestrator + claude → --permission-mode auto in command."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["claude"])
        assert "--permission-mode" in args and "auto" in args, f"Expected --permission-mode auto in {args}"

    def test_orchestrator_claude2_gets_auto(self):
        """orchestrator + claude2 → --permission-mode auto in command."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["claude2"])
        assert "--permission-mode" in args and "auto" in args, f"Expected --permission-mode auto in {args}"

    def test_orchestrator_agy_no_auto(self):
        """orchestrator + agy → no --permission-mode."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["agy"])
        assert "--permission-mode" not in args, f"Did not expect --permission-mode in {args}"

    def test_oracle_claude_no_auto(self):
        """oracle + claude → no --permission-mode."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = True
        sm.session_type = "oracle"

        args = _capture_exec(sm, ["claude"])
        assert "--permission-mode" not in args, f"Did not expect --permission-mode in {args}"

    def test_first_launch_no_auto(self):
        """_just_restarted=False → no --permission-mode even for orchestrator+claude."""
        sm, _pty, _tok = make_manager()
        sm._just_restarted = False
        sm.session_type = "orchestrator"

        args = _capture_exec(sm, ["claude"])
        assert "--permission-mode" not in args, f"Did not expect --permission-mode in {args}"


# ---------------------------------------------------------------------------
# T-329: _get_claude_skill_cmd helper
# ---------------------------------------------------------------------------

class TestGetClaudeSkillCmd:
    def test_namespaced_cmd_claude_orchestrate(self, tmp_path):
        """_get_claude_skill_cmd('orchestrate') → '/claude:orchestrate' when file exists."""
        import agentflow.shell.process_manager as _pm
        commands_base = tmp_path / ".claude" / "commands"
        claude_sub = commands_base / "claude"
        claude_sub.mkdir(parents=True)
        (claude_sub / "orchestrate.md").write_text("# orchestrate")

        with patch.object(_pm, "_COMMANDS_DIR", commands_base):
            result = _get_claude_skill_cmd("orchestrate")
        assert result == "/claude:orchestrate"

    def test_namespaced_cmd_claude_oracle(self, tmp_path):
        """_get_claude_skill_cmd('oracle') → '/claude:oracle' when file exists."""
        import agentflow.shell.process_manager as _pm
        commands_base = tmp_path / ".claude" / "commands"
        claude_sub = commands_base / "claude"
        claude_sub.mkdir(parents=True)
        (claude_sub / "oracle.md").write_text("# oracle")

        with patch.object(_pm, "_COMMANDS_DIR", commands_base):
            result = _get_claude_skill_cmd("oracle")
        assert result == "/claude:oracle"

    def test_root_level_fallback(self, tmp_path):
        """When file is at commands root level (no subdir) → /orchestrate."""
        import agentflow.shell.process_manager as _pm
        commands_base = tmp_path / ".claude" / "commands"
        commands_base.mkdir(parents=True)
        (commands_base / "orchestrate.md").write_text("# orchestrate")

        with patch.object(_pm, "_COMMANDS_DIR", commands_base):
            result = _get_claude_skill_cmd("orchestrate")
        assert result == "/orchestrate"

    def test_not_found_fallback(self, tmp_path):
        """When neither subdir nor root has the file → /orchestrate (bare fallback)."""
        import agentflow.shell.process_manager as _pm
        commands_base = tmp_path / ".claude" / "commands"
        commands_base.mkdir(parents=True)

        with patch.object(_pm, "_COMMANDS_DIR", commands_base):
            result = _get_claude_skill_cmd("orchestrate")
        assert result == "/orchestrate"

    def test_nonexistent_commands_dir_fallback(self, tmp_path):
        """When commands dir does not exist → /orchestrate (bare fallback)."""
        import agentflow.shell.process_manager as _pm
        commands_base = tmp_path / ".claude" / "commands"  # Not created

        with patch.object(_pm, "_COMMANDS_DIR", commands_base):
            result = _get_claude_skill_cmd("orchestrate")
        assert result == "/orchestrate"

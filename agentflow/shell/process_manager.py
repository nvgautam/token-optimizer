"""Process manager logic extracted from session_manager."""
from __future__ import annotations
import os
import time
import signal
from pathlib import Path

# T-329: base directory for resolving namespaced slash commands.
# Tests patch this module-level constant to inject a fake directory.
_COMMANDS_DIR: Path = Path.home() / ".claude" / "commands"


def _get_claude_skill_cmd(skill_name: str) -> str:
    """Return the slash command string for *skill_name*, resolved against _COMMANDS_DIR.

    Resolution order:
    1. Iterate subdirectories of _COMMANDS_DIR alphabetically; return
       ``/{subdir}:{skill_name}`` for the first subdir that contains
       ``{skill_name}.md``.
    2. If ``{skill_name}.md`` exists at the root of _COMMANDS_DIR, return
       ``/{skill_name}`` (no namespace).
    3. Fallback: return ``/{skill_name}``.
    """
    base: Path = _COMMANDS_DIR
    if not base.is_dir():
        return f"/{skill_name}"

    # Check subdirectories first (alphabetical so "claude" wins in the known layout).
    for subdir in sorted(p for p in base.iterdir() if p.is_dir()):
        if (subdir / f"{skill_name}.md").is_file():
            return f"/{subdir.name}:{skill_name}"

    # Check root level.
    if (base / f"{skill_name}.md").is_file():
        return f"/{skill_name}"

    return f"/{skill_name}"


def handle_enter_restarting(manager) -> None:
    manager._just_restarted = True
    # T-209: reset context_fill to 0 before spawning so new session starts clean
    manager._clear_signal_files()
    manager.restart_child()
    try:
        os.write(1, b"\x1b[0m")
    except OSError as e:
        manager._log_audit({"event": "reset_ansi_write_error", "error": str(e)})

def restart_child(manager) -> None:
    """Kills the active Claude child process and restarts it."""
    if not getattr(manager._pty, "_command", None):
        manager._log_audit({"event": "restart_session_aborted", "reason": "_command_missing"})
        return
    manager._log_audit({
        "event": "restart_session",
        "command": manager._pty._command,
        "CLAUDE_CONFIG_DIR": os.environ.get("CLAUDE_CONFIG_DIR"),
    })
    manager._last_restart_ts = time.monotonic()
    pid = getattr(manager._pty, "child_pid", None)
    manager._log_audit({"event": "kill_child", "pid": pid, "signal": "SIGTERM", "caller": "restart_child"})
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            t0 = time.monotonic()
            killed = False
            while time.monotonic() - t0 < 2.0:
                try:
                    p, status = os.waitpid(pid, os.WNOHANG)
                    if p == pid:
                        killed = True
                        break
                except ChildProcessError:
                    killed = True
                    break
                time.sleep(0.05)
            if not killed:
                manager._log_audit({"event": "kill_child", "pid": pid, "signal": "SIGKILL", "caller": "restart_child_escalate"})
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError as e:
                    manager._log_audit({"event": "kill_child_sigkill_error", "error": str(e)})
                from agentflow.shell.handoff_handler import _reap_child
                _reap_child(pid)
        except OSError as e:
            manager._log_audit({"event": "restart_child_kill_error", "error": str(e)})

    manager._clear_signal_files()
    manager._spawn_new_child()
    # T-150: reset token state so counts do not carry over from the previous session
    manager._last_accumulated_tokens = 0
    if hasattr(manager._tokenizer, "reset"):
        manager._tokenizer.reset()
    manager._log_audit({"event": "restart_done", "state_before": manager._state_machine.state.value})
    manager._state_machine.transition("restart_done")

def spawn_new_child(manager) -> None:
    command = getattr(manager._pty, "_command", None)
    if not command:
        if hasattr(manager._pty, "_exited"):
            manager._pty._exited = False
        return

    # T-195/T-329: Append skill as positional arg when restarting with known session_type.
    # T-329: Use _get_claude_skill_cmd to resolve the correct namespaced command path
    # (e.g. /claude:orchestrate) rather than hard-coding /orchestrate or /oracle.
    if getattr(manager, "_just_restarted", False):
        _stype = getattr(manager, "session_type", None)
        skill = "oracle" if _stype == "oracle" else "orchestrate" if _stype == "orchestrator" else None
        if skill:
            command = list(command) + [_get_claude_skill_cmd(skill)]

    # T-243: Pass --permission-mode auto to claude/claude2 orchestrator restarts (not agy)
    if getattr(manager, "_just_restarted", False):
        _stype = getattr(manager, "session_type", None)
        cmd_name = os.path.basename(str(command[0])) if command else ""
        if _stype == "orchestrator" and cmd_name in ("claude", "claude2"):
            command = list(command) + ["--permission-mode", "auto"]

    # T-196: Append pre-resolved task context if available
    try:
        from pathlib import Path
        import json
        current_round_path = Path(".agentflow/current_round.json")
        if current_round_path.exists():
            data = json.loads(current_round_path.read_text())
            # T-218: Note when session_id field is absent (legacy fallback)
            if "session_id" not in data:
                manager._log_audit({"event": "spawn_new_child_no_session_id", "note": "legacy fallback"})
            task_ctx = data.get("task_ctx")
            if isinstance(task_ctx, dict):
                task_id = task_ctx.get("task_id", "")
                title = task_ctx.get("title", "")
                deps = task_ctx.get("deps", [])
                estimated_lines = task_ctx.get("estimated_lines", 0)

                # Format deps as comma-separated string or NONE
                deps_str = ",".join(deps) if deps else "NONE"

                # Build TASK_CTX argument
                task_ctx_arg = f"TASK_CTX:task_id={task_id};title={title};deps={deps_str};estimated_lines={estimated_lines}"
                command = list(command) + [task_ctx_arg]
    except Exception as e:
        manager._log_audit({"event": "spawn_new_child_task_ctx_error", "error": str(e)})

    import pty
    import fcntl
    import termios
    import struct

    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        os.environ["AGENTFLOW_PTY"] = "1"
        try:
            os.execvp(command[0], command)
        except Exception:
            os._exit(127)

    manager._log_audit({"event": "spawn_child", "pid": child_pid})
    manager._pty.child_pid = child_pid
    old_fd = getattr(manager._pty, "master_fd", None)
    if old_fd is not None:
        try:
            os.close(old_fd)
        except OSError:
            pass
    manager._pty.master_fd = master_fd
    manager._pty._exited = False
    manager._pty._exit_code = None
    # Restore callbacks cleared by the previous child's exit
    manager._pty._on_exit = manager._on_session_exit
    manager._pty._on_output = manager._handle_output

    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    try:
        packed = termios.tcgetwinsize(0) if hasattr(termios, "tcgetwinsize") else None
        if packed is None:
            buf = b"\x00" * 8
            result = fcntl.ioctl(1, termios.TIOCGWINSZ, buf)
            rows, cols, _, _ = struct.unpack("HHHH", result)
        else:
            rows, cols = packed
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except Exception as e:
        manager._log_audit({"event": "spawn_new_child_termios_error", "error": str(e)})

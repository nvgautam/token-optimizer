"""Process manager logic extracted from session_manager."""
from __future__ import annotations
import os
import time
import signal

def handle_enter_restarting(manager) -> None:
    manager._just_restarted = True
    manager.restart_child()
    try:
        os.write(1, b"\x1b[0m")
    except OSError:
        pass

def restart_child(manager) -> None:
    """Kills the active Claude child process and restarts it."""
    if not getattr(manager._pty, "_command", None):
        manager._log_audit({"event": "restart_session_aborted", "reason": "_command_missing"})
        return
    manager._log_audit({"event": "restart_session"})
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
                except OSError:
                    pass
                from agentflow.shell.handoff_handler import _reap_child
                _reap_child(pid)
        except OSError:
            pass

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
    except Exception:
        pass

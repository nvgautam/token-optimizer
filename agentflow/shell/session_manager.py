"""PTY session manager — handoff, countdown, idx injection.

Refactored to drive a file-based state machine. Stdlib-only.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import pathlib
import re
import signal
import time
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from agentflow.shell.countdown import countdown  # noqa: F401
from agentflow.shell.state_machine import StateMachine, States

_DEFAULTS = {
    "handoff_primary_tokens": 80000,
    "handoff_safety_tokens": 120000,
    "handoff_hard_ceiling_tokens": 150000,
    "restart_delay_seconds": 5
}
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDhJlsu]")
_READ_PATH_RE = re.compile(
    r"Read\([^)]*?file_path\s*=\s*[\"']([^\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']|"
    r"Read\([\"']([^\s\"')]+\.(?:py|md|json|toml|yaml|yml|txt))[\"']\)|"
    r"(?:^|\b)Read\s+tool\s+[\"']?([^\s\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']?",
    re.MULTILINE
)

class SessionManager:
    """Monitors PTY I/O; drives state machine via file-polling and token thresholds."""

    def __init__(self, pty_wrapper, tokenizer, config: dict) -> None:
        cfg = dict(_DEFAULTS)
        try:
            with open(pathlib.Path.home() / ".agentflow" / "config.toml", "rb") as fh:
                cfg.update(tomllib.load(fh).get("shell", {}))
        except Exception:
            pass
        self._config = {**cfg, **(config or {})}
        self._pty, self._tokenizer = pty_wrapper, tokenizer
        self.session_type: Optional[str] = None
        self._turn_count = 0
        self._manual_handoff = self._injecting = self._last_had_content = False
        self._handoff_event = self._handoff_thread = None
        self._current_turn_output_tokens, self._turn_output_history, self._task_start_tokens = 0, [], {}
        self._arm = self._read_arm_file()
        self._cwd_hash = hashlib.sha256(os.getcwd().encode()).hexdigest()
        self._last_idx_injected = None
        self._last_accumulated_tokens = 0
        self._last_restart_ts: float = 0.0
        self._current_trigger = "auto"
        
        # State machine initialization
        self._state_machine = StateMachine(
            initial_state=States.IDLE,
            threshold_tokens=self._config["handoff_primary_tokens"]
        )
        self._state_machine.on_enter_restarting = self.on_enter_restarting
        self._state_machine.on_enter_handoff_pending = self.on_enter_handoff_pending
        self._state_machine.on_enter_idle = self.on_enter_idle
        self._state_machine.on_enter_dead_child = self.on_enter_dead_child
        self._just_restarted = False

        self._update_last_current_round_mtime()
        if self._current_round_path.exists() and not self._task_complete_path.exists():
            self._state_machine.state = States.TASK_RUNNING

        # Wire up wrappers
        pty_wrapper._on_output = self._handle_output
        pty_wrapper._on_exit = self._on_session_exit
        self._run_stale_index_guard()

    @property
    def _project_root(self) -> pathlib.Path:
        return getattr(self, "_project_root_override", None) or pathlib.Path.cwd()

    def _auto_handoff_disabled(self) -> bool:
        return (self._project_root / ".agentflow" / "handoff_disabled").exists()

    @_project_root.setter
    def _project_root(self, val: pathlib.Path) -> None:
        self._project_root_override = val

    @property
    def _current_round_path(self) -> pathlib.Path:
        return getattr(self, "_current_round_path_override", None) or (self._project_root / ".agentflow" / "current_round.json")

    @_current_round_path.setter
    def _current_round_path(self, val: pathlib.Path) -> None:
        self._current_round_path_override = val

    @property
    def _task_complete_path(self) -> pathlib.Path:
        return getattr(self, "_task_complete_path_override", None) or (self._project_root / ".agentflow" / "task_complete.json")

    @_task_complete_path.setter
    def _task_complete_path(self, val: pathlib.Path) -> None:
        self._task_complete_path_override = val

    @property
    def _handoff_complete_path(self) -> pathlib.Path:
        return getattr(self, "_handoff_complete_path_override", None) or (self._project_root / ".agentflow" / "handoff_complete.json")

    @_handoff_complete_path.setter
    def _handoff_complete_path(self, val: pathlib.Path) -> None:
        self._handoff_complete_path_override = val

    @property
    def _handoff_in_progress(self) -> bool:
        return self._state_machine.state in (States.HANDOFF_PENDING, States.RESTARTING)

    @_handoff_in_progress.setter
    def _handoff_in_progress(self, val: bool) -> None:
        if val:
            if self._state_machine.state != States.HANDOFF_PENDING:
                self.trigger_handoff(trigger="manual")
        else:
            if self._state_machine.state in (States.HANDOFF_PENDING, States.RESTARTING):
                self._state_machine.transition("handoff_aborted")

    def _read_arm_file(self) -> str | None:
        try:
            return (pathlib.Path.cwd() / ".agentflow" / "verbosity_ab_arm.txt").read_text("utf-8").strip() or None
        except Exception:
            return None

    def _log_audit(self, entry: dict) -> None:
        log_path = self._project_root / ".agentflow" / "pty_audit.jsonl"
        if not log_path.parent.exists():
            return
        try:
            entry = {**entry, "ts": datetime.datetime.now().isoformat(), "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def on_idle_tick(self) -> None:
        self.poll()
        now = time.monotonic()
        if not hasattr(self, "_last_guard_tick") or now - self._last_guard_tick > 2.0:
            self._last_guard_tick = now
            self._run_stale_index_guard()

    def _run_stale_index_guard(self) -> None:
        try:
            root = pathlib.Path.cwd().resolve()
            h = hashlib.sha256(str(root).encode()).hexdigest()
            cd = pathlib.Path("~/.agentflow/cache").expanduser().resolve() / h / "index"
            files = []
            if cd.exists():
                for r, _, fs in os.walk(cd):
                    for f in fs:
                        if f.endswith(".idx"):
                            ip = pathlib.Path(r) / f
                            sp = root / str(ip.relative_to(cd))[:-4]
                            if sp.exists() and sp.stat().st_mtime > ip.stat().st_mtime:
                                files.append(str(sp))
            for r, ds, fs in os.walk(root):
                ds[:] = [d for d in ds if d not in {".git", ".venv", "node_modules", "__pycache__", ".agentflow", ".pytest_cache"}]
                for f in fs:
                    sp = pathlib.Path(r) / f
                    if sp.suffix in (".py", ".md"):
                        ip = cd / sp.relative_to(root).parent / f"{f}.idx"
                        if not ip.exists():
                            try:
                                with open(sp, "r", encoding="utf-8", errors="ignore") as fh:
                                    if len([fh.readline() for _ in range(50)]) >= 50:
                                        files.append(str(sp))
                            except Exception:
                                pass
            files = list(set(files))
            if files:
                import subprocess
                import sys
                subprocess.run([sys.executable, str(pathlib.Path(__file__).parent.parent / "hooks" / "write_indexer.py")] + files, capture_output=True)
        except Exception:
            pass

    def poll(self) -> None:
        """Poll signal files and drive the state machine."""
        # Any state -> DEAD_CHILD on PTY master fd EOF or process exit
        if getattr(self._pty, "_exited", False):
            self._state_machine.transition("pty_eof")
            return

        state = self._state_machine.state

        if state == States.IDLE:
            if self._current_round_path.exists():
                try:
                    mtime = self._current_round_path.stat().st_mtime
                    if mtime > self._last_current_round_mtime:
                        self._state_machine.transition("current_round_written")
                except Exception:
                    pass
            elif not self._auto_handoff_disabled() and (
                self._last_accumulated_tokens >= self._config.get("handoff_safety_tokens", 120000) or
                self._last_accumulated_tokens >= self._config.get("handoff_hard_ceiling_tokens", 150000)
            ):
                self._state_machine.transition("trigger_handoff")

        elif state == States.TASK_RUNNING:
            if self._task_complete_path.exists():
                self._state_machine.transition("task_complete_written")

        elif state == States.TASK_COMPLETE:
            self._state_machine.transition("check_tokens", tokens=self._last_accumulated_tokens)

        elif state == States.HANDOFF_PENDING:
            if self._handoff_complete_path.exists():
                self._state_machine.transition("handoff_complete_written")

    def _update_last_current_round_mtime(self) -> None:
        try:
            if self._current_round_path.exists():
                self._last_current_round_mtime = self._current_round_path.stat().st_mtime
            else:
                self._last_current_round_mtime = 0.0
        except Exception:
            self._last_current_round_mtime = 0.0

    def _clear_signal_files(self) -> None:
        for path in [self._task_complete_path, self._handoff_complete_path]:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    def on_enter_handoff_pending(self) -> None:
        try:
            self._pty.write_input("/handoff\n")
        except OSError:
            self._log_audit({"event": "handoff_aborted", "trigger": self._current_trigger, "tokens": self._last_accumulated_tokens})
            self._state_machine.transition("handoff_aborted")
            raise

    def _run_handoff_loop(self, trigger: str) -> None:
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            if getattr(self._pty, "_exited", False):
                self._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": self._last_accumulated_tokens})
                self._state_machine.transition("pty_eof")
                return

            if self._handoff_complete_path.exists():
                self._state_machine.transition("handoff_complete_written")
                return

            try:
                chunk = self._pty.read_output(timeout=0.01)
                if chunk:
                    try:
                        os.write(1, chunk)
                    except OSError:
                        pass
                    text = chunk.decode("utf-8", errors="replace")
                    if "HANDOFF_COMPLETE" in text:
                        self._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
                        self._handoff_complete_path.write_text("{}", encoding="utf-8")
                        self._state_machine.transition("handoff_complete_written")
                        return
            except OSError:
                self._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": self._last_accumulated_tokens})
                self._state_machine.transition("handoff_aborted")
                return

            time.sleep(0.01)

        self._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": self._last_accumulated_tokens})
        self._state_machine.transition("handoff_aborted")

    def on_enter_restarting(self) -> None:
        self._just_restarted = True
        self.restart_child()

    def on_enter_idle(self) -> None:
        self._update_last_current_round_mtime()
        self._clear_signal_files()
        if self._just_restarted:
            self._just_restarted = False
            cmd = "oracle" if self.session_type == "oracle" else "orchestrate" if self.session_type == "orchestrator" else None
            if cmd:
                try:
                    self._pty.write_input(f"/{cmd}\n")
                except OSError:
                    pass

    def on_enter_dead_child(self) -> None:
        self._log_audit({"event": "dead_child_detected"})

    def restart_child(self) -> None:
        """Kills the active Claude child process and restarts it."""
        self._log_audit({"event": "restart_session"})
        self._last_restart_ts = time.monotonic()
        pid = getattr(self._pty, "child_pid", None)
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
                    try:
                        os.kill(pid, signal.SIGKILL)
                        os.waitpid(pid, 0)
                    except OSError:
                        pass
            except OSError:
                pass

        self._clear_signal_files()
        self._spawn_new_child()
        self._state_machine.transition("restart_done")

    def _spawn_new_child(self) -> None:
        command = getattr(self._pty, "_command", None)
        if not command:
            if hasattr(self._pty, "_exited"):
                self._pty._exited = False
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

        self._pty.child_pid = child_pid
        old_fd = getattr(self._pty, "master_fd", None)
        if old_fd is not None:
            try:
                os.close(old_fd)
            except OSError:
                pass
        self._pty.master_fd = master_fd
        self._pty._exited = False
        self._pty._exit_code = None

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

    def _handle_output(self, chunk: bytes) -> None:
        text = chunk.decode("utf-8", errors="replace")
        clean = self._ansi_strip(text)
        
        self.poll()

        detected_path = self._detect_read_path(clean)
        if detected_path and detected_path.startswith("/"):
            cwd = os.getcwd() + "/"
            detected_path = detected_path[len(cwd):] if detected_path.startswith(cwd) else None
        if detected_path and detected_path != self._last_idx_injected:
            self._last_idx_injected = detected_path

        if "/clear" in text:
            self._log_audit({"event": "clear_detected"})
            if self.session_type is not None:
                self._log_audit({"event": "session_type_transition", "old": self.session_type, "new": None})
            self.session_type, self._turn_count = None, 0
            if self._manual_handoff:
                self._manual_handoff = False
                self._log_audit({"event": "manual_handoff_reset"})
            if hasattr(self._tokenizer, "reset"):
                self._tokenizer.reset()
            self._update_session_file()

        if self.session_type is None:
            new_st = "oracle" if "/oracle" in text else "orchestrator" if "/orchestrate" in text else None
            if new_st:
                self._log_audit({"event": "session_type_transition", "old": self.session_type, "new": new_st})
                self.session_type, self._turn_count, self._arm = new_st, 0, self._read_arm_file()
                self._update_session_file()

        if "/handoff" in text:
            if not self._manual_handoff:
                self._manual_handoff = True
                self._log_audit({"event": "manual_handoff_set"})

        if self._last_had_content and "\n\n" in text:
            self._turn_count += 1
            if self._turn_count == 1:
                self._arm = self._read_arm_file()
            self._last_had_content = False
            self._turn_output_history.append(self._current_turn_output_tokens)
            if len(self._turn_output_history) > 10:
                self._turn_output_history = self._turn_output_history[-10:]

            lp = self._project_root / ".agentflow" / "verbosity_log.jsonl"
            if lp.parent.exists():
                try:
                    entry = {"ts": datetime.datetime.now().isoformat(), "session_type": self.session_type, "turn": self._turn_count, "output_tokens": self._current_turn_output_tokens, "arm": self._arm, "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
                    with open(lp, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry) + "\n")
                except Exception:
                    pass
            self._current_turn_output_tokens = 0
            self._last_idx_injected = None
            self._run_stale_index_guard()

        if text.strip():
            self._last_had_content = True

        if self._state_machine.state == States.HANDOFF_PENDING and "HANDOFF_COMPLETE" in clean:
            try:
                self._handoff_complete_path.parent.mkdir(parents=True, exist_ok=True)
                self._handoff_complete_path.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
            except Exception:
                pass
            self._state_machine.transition("handoff_complete_written")

        self._current_turn_output_tokens += self._tokenizer.count_tokens(text, "claude")
        total = self._tokenizer.accumulate(text, "claude")
        self._last_accumulated_tokens = total

        start_m = re.search(r"AGENTFLOW_TASK_START:([A-Za-z0-9_-]+)", clean)
        if start_m:
            self._task_start_tokens[start_m.group(1)] = total

        complete_m = re.search(r"AGENTFLOW_TASK_COMPLETE:([A-Za-z0-9_-]+)", clean)
        if complete_m:
            tid = complete_m.group(1)
            if tid in self._task_start_tokens:
                self._record_task_tokens(tid, total - self._task_start_tokens.pop(tid))

        _restart_cooldown = 30.0
        _since_restart = time.monotonic() - self._last_restart_ts
        if not self._manual_handoff and not self._auto_handoff_disabled() and self._state_machine.state not in (States.HANDOFF_PENDING, States.RESTARTING) and _since_restart >= _restart_cooldown:
            primary = self._config["handoff_primary_tokens"]
            safety = self._config["handoff_safety_tokens"]
            ceiling = self._config["handoff_hard_ceiling_tokens"]
            self._log_audit({"event": "token_evaluation", "accumulated_tokens": total, "primary": primary, "safety": safety, "ceiling": ceiling})
            triggered = False

            # Primary: 80K + a scheduled task just completed (no task in-flight)
            task_just_completed = complete_m is not None
            task_in_flight = bool(self._task_start_tokens) or self._state_machine.state == States.TASK_RUNNING
            if not triggered and total >= primary and task_just_completed and not task_in_flight:
                self.trigger_handoff(trigger="auto-primary")
                triggered = True

            # Safety net: 120K + no task in-flight
            if not triggered and total >= safety and not task_in_flight:
                self.trigger_handoff(trigger="auto-safety")
                triggered = True

            # Hard ceiling: 150K unconditional
            if not triggered and total >= ceiling:
                self.trigger_handoff(trigger="auto-ceiling")

    def _record_task_tokens(self, task_id: str, delta: int) -> None:
        rp, el, fc = self._project_root / ".agentflow" / "current_round.json", 0, 0
        try:
            d = json.loads(rp.read_text("utf-8")) if rp.exists() else {}
            el = d.get("estimated_lines_per_task", {}).get(task_id, 0)
            fc = d.get("file_counts_per_task", {}).get(task_id, 0)
        except Exception:
            pass
        log_path = pathlib.Path.home() / ".agentflow" / "task_token_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"task_id": task_id, "session_type": self.session_type, "token_delta": delta, "estimated_lines": el, "file_count": fc, "timestamp": datetime.datetime.now().isoformat()}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _ansi_strip(self, text: str) -> str:
        return _ANSI_ESCAPE_RE.sub("", text)

    def _detect_read_path(self, text: str) -> str | None:
        m = _READ_PATH_RE.search(text)
        return next((g for g in m.groups() if g), None) if m else None

    def _on_session_exit(self, exit_code: int) -> None:
        pass

    def trigger_handoff(self, trigger: str = "auto") -> None:
        self._current_trigger = trigger
        if getattr(self._pty, "_exited", False):
            self._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": self._last_accumulated_tokens})
            self._state_machine.transition("pty_eof")
            return

        self._log_audit({"event": "trigger_handoff", "trigger": trigger})
        try:
            self._state_machine.transition("trigger_handoff")
        except OSError:
            return

        if self._state_machine.state != States.HANDOFF_PENDING:
            return

        in_pytest = "PYTEST_CURRENT_TEST" in os.environ
        run_sync_loop = in_pytest and not getattr(self, "_force_async_handoff", False)
        
        if run_sync_loop:
            self._run_handoff_loop(trigger)

    def _restart_session(self) -> None:
        self._state_machine.transition("restart_session")

    def _update_session_file(self) -> None:
        sid = os.environ.get("AGENTFLOW_SESSION_ID")
        if not sid:
            return
        sf = pathlib.Path.home() / ".agentflow" / "sessions" / f"{sid}.json"
        try:
            data = json.loads(sf.read_text("utf-8")) if sf.exists() else {}
        except Exception:
            data = {}
        try:
            data.setdefault("started_at", datetime.datetime.now().isoformat())
            data.update({"arm": self._arm, "session_type": self.session_type})
            sf.parent.mkdir(parents=True, exist_ok=True)
            sf.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

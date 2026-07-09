"""PTY session manager — handoff, countdown, idx injection.

Refactored to drive a file-based state machine. Stdlib-only.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import pathlib
import time
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from agentflow.shell.countdown import countdown  # noqa: F401
from agentflow.shell.state_machine import StateMachine, States

_DEFAULTS = {
    "handoff_primary_tokens": 80000,  # T-151: only threshold that triggers auto-handoff
    "restart_delay_seconds": 5
}


class SessionManager:
    """Monitors PTY I/O; drives state machine via file-polling and token thresholds."""

    def __init__(self, pty_wrapper, tokenizer, config: dict) -> None:
        cfg = dict(_DEFAULTS)
        try:
            with open(pathlib.Path.home() / ".agentflow" / "config.toml", "rb") as fh:
                toml_cfg = tomllib.load(fh)
                cfg.update(toml_cfg.get("shell", {}))
                # Provider-specific overrides: [shell.gemini] / [shell.claude]
                provider = (getattr(pty_wrapper, "_command", None) or "").split("/")[-1]
                if provider and provider in toml_cfg.get("shell", {}):
                    cfg.update(toml_cfg["shell"][provider])
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
        self._deadline_state = None
        self._deadline_entered_at: float = 0.0
        
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
        self._sync_session_type()

    @property
    def _project_root(self) -> pathlib.Path: return getattr(self, "_project_root_override", None) or pathlib.Path.cwd()
    @_project_root.setter
    def _project_root(self, val: pathlib.Path) -> None: self._project_root_override = val

    def _auto_handoff_disabled(self) -> bool: return (self._project_root / ".agentflow" / "handoff_disabled").exists()

    @property
    def _current_round_path(self) -> pathlib.Path: return getattr(self, "_current_round_path_override", None) or (self._project_root / ".agentflow" / "current_round.json")
    @_current_round_path.setter
    def _current_round_path(self, val: pathlib.Path) -> None: self._current_round_path_override = val

    @property
    def _task_complete_path(self) -> pathlib.Path: return getattr(self, "_task_complete_path_override", None) or (self._project_root / ".agentflow" / "task_complete.json")
    @_task_complete_path.setter
    def _task_complete_path(self, val: pathlib.Path) -> None: self._task_complete_path_override = val

    @property
    def _handoff_complete_path(self) -> pathlib.Path: return getattr(self, "_handoff_complete_path_override", None) or (self._project_root / ".agentflow" / "handoff_complete.json")
    @_handoff_complete_path.setter
    def _handoff_complete_path(self, val: pathlib.Path) -> None: self._handoff_complete_path_override = val

    @property
    def _handoff_in_progress(self) -> bool: return self._state_machine.state in (States.HANDOFF_PENDING, States.RESTARTING)
    @_handoff_in_progress.setter
    def _handoff_in_progress(self, val: bool) -> None:
        if val:
            if self._state_machine.state != States.HANDOFF_PENDING: self.trigger_handoff(trigger="manual")
        else:
            if self._state_machine.state in (States.HANDOFF_PENDING, States.RESTARTING): self._state_machine.transition("handoff_aborted")

    def _read_arm_file(self) -> str | None:
        try: return (pathlib.Path.cwd() / ".agentflow" / "verbosity_ab_arm.txt").read_text("utf-8").strip() or None
        except Exception: return None

    def _log_audit(self, entry: dict) -> None:
        lp = self._project_root / ".agentflow" / "pty_audit.jsonl"
        if not lp.parent.exists(): return
        try:
            entry = {**entry, "ts": datetime.datetime.now().isoformat(), "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
            with open(lp, "a", encoding="utf-8") as fh: fh.write(json.dumps(entry) + "\n")
        except Exception: pass

    def on_idle_tick(self) -> None:
        self._sync_session_type()
        self.poll()
        now = time.monotonic()
        if not hasattr(self, "_last_guard_tick") or now - self._last_guard_tick > 60.0:
            self._last_guard_tick = now
            self._run_stale_index_guard()

    def _apply_session_threshold(self) -> None:
        if self.session_type == "oracle":
            threshold = self._config.get("oracle_threshold_tokens", 50000)
        elif self.session_type == "orchestrator":
            threshold = self._config.get("handoff_primary_tokens", 80000)
        else:
            return
        if self._state_machine.threshold_tokens != threshold:
            self._state_machine.threshold_tokens = threshold

    def _sync_session_type(self) -> None:
        if self.session_type is None:
            sig = self._project_root / ".agentflow" / "session_type"
            try:
                if sig.exists():
                    st = sig.read_text("utf-8").strip()
                    if st in ("oracle", "orchestrator"):
                        self.session_type = st
                        self._update_session_file()
            except Exception:
                pass
        self._apply_session_threshold()

    def _run_stale_index_guard(self) -> None:
        from agentflow.shell.stale_index_guard import run_stale_index_guard
        run_stale_index_guard()

    def poll(self) -> None:
        from agentflow.shell.handoff_handler import poll_session
        poll_session(self)

    def _update_last_current_round_mtime(self) -> None:
        try: self._last_current_round_mtime = self._current_round_path.stat().st_mtime if self._current_round_path.exists() else 0.0
        except Exception: self._last_current_round_mtime = 0.0

    def _clear_signal_files(self) -> None:
        for path in [self._task_complete_path, self._handoff_complete_path]:
            try:
                if path.exists(): path.unlink()
            except Exception: pass

    def on_enter_handoff_pending(self) -> None:
        from agentflow.shell.handoff_handler import handle_enter_handoff_pending
        handle_enter_handoff_pending(self)



    def on_enter_restarting(self) -> None:
        from agentflow.shell.process_manager import handle_enter_restarting
        handle_enter_restarting(self)

    def on_enter_idle(self) -> None:
        self._update_last_current_round_mtime()
        self._clear_signal_files()
        if self._just_restarted:
            self._just_restarted = False
            cmd = "oracle" if self.session_type == "oracle" else "orchestrate" if self.session_type == "orchestrator" else None
            if cmd:
                try: self._pty.write_input(f"/{cmd}\r")
                except OSError: pass

    def on_enter_dead_child(self) -> None:
        self._log_audit({"event": "dead_child_detected"})

    def restart_child(self) -> None:
        """Kills the active Claude child process and restarts it."""
        from agentflow.shell.process_manager import restart_child
        restart_child(self)

    def _spawn_new_child(self) -> None:
        from agentflow.shell.process_manager import spawn_new_child
        spawn_new_child(self)

    def _handle_output(self, chunk: bytes) -> None:
        from agentflow.shell.output_handler import handle_output
        handle_output(self, chunk)

    def _record_task_tokens(self, task_id: str, delta: int) -> None:
        from agentflow.shell.output_handler import record_task_tokens
        record_task_tokens(self, task_id, delta)

    def _ansi_strip(self, text: str) -> str:
        from agentflow.shell.output_handler import ansi_strip
        return ansi_strip(text)

    def _detect_read_path(self, text: str) -> str | None:
        from agentflow.shell.output_handler import detect_read_path
        return detect_read_path(text)

    def _on_session_exit(self, exit_code: int) -> None:
        """Called by PTYWrapper when the child process exits."""
        self._log_audit({"event": "session_exit", "exit_code": exit_code})
        # If handoff just completed, restart rather than die — oracle exits
        # immediately after writing handoff_complete.json; treat as restart signal.
        if (self._state_machine.state == States.HANDOFF_PENDING
                and self._handoff_complete_path.exists()):
            self._state_machine.transition("handoff_complete_written")
            return
        try:
            self._state_machine.transition("pty_eof")
        except Exception:
            pass

    def trigger_handoff(self, trigger: str = "auto") -> None:
        from agentflow.shell.handoff_handler import trigger_handoff
        trigger_handoff(self, trigger)

    def _restart_session(self) -> None:
        self._state_machine.transition("restart_session")

    def _update_session_file(self) -> None:
        sid = os.environ.get("AGENTFLOW_SESSION_ID")
        if not sid: return
        sf = pathlib.Path.home() / ".agentflow" / "sessions" / f"{sid}.json"
        try: data = json.loads(sf.read_text("utf-8")) if sf.exists() else {}
        except Exception: data = {}
        try:
            data.setdefault("started_at", datetime.datetime.now().isoformat())
            data.update({"arm": self._arm, "session_type": self.session_type})
            sf.parent.mkdir(parents=True, exist_ok=True)
            sf.write_text(json.dumps(data), encoding="utf-8")
        except Exception: pass

"""PTY session manager — handoff, countdown, idx injection.

Stdlib-only. Zero LLM calls. Fully deterministic.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import pathlib
import re
import time
from typing import Optional
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore
from agentflow.shell.countdown import countdown

_DEFAULTS = {"handoff_primary_tokens": 80000, "handoff_safety_tokens": 120000, "handoff_hard_ceiling_tokens": 150000, "restart_delay_seconds": 5}
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDhJlsu]")
_READ_PATH_RE = re.compile(r"Read\([^)]*?file_path\s*=\s*[\"']([^\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']|Read\([\"']([^\s\"')]+\.(?:py|md|json|toml|yaml|yml|txt))[\"']\)|(?:^|\b)Read\s+tool\s+[\"']?([^\s\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']?", re.MULTILINE)

class SessionManager:
    """Monitors PTY I/O; injects IDX banners and triggers handoff on threshold."""

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
        self._manual_handoff = self._injecting = self._handoff_in_progress = self._last_had_content = False
        self._handoff_event = self._handoff_thread = None
        self._current_turn_output_tokens, self._turn_output_history, self._task_start_tokens = 0, [], {}
        self._arm = self._read_arm_file()
        self._cwd_hash = hashlib.sha256(os.getcwd().encode()).hexdigest()
        self._last_idx_injected = None
        self._last_accumulated_tokens = 0
        self._last_restart_ts: float = 0.0
        pty_wrapper._on_output = self._handle_output
        pty_wrapper._on_exit = self._on_session_exit
        self._run_stale_index_guard()

    def _read_arm_file(self) -> str | None:
        try:
            return (pathlib.Path.cwd() / ".agentflow" / "verbosity_ab_arm.txt").read_text("utf-8").strip() or None
        except Exception:
            return None

    def _log_audit(self, entry: dict) -> None:
        log_path = pathlib.Path.cwd() / ".agentflow" / "pty_audit.jsonl"
        if not log_path.parent.exists():
            return
        try:
            entry = {**entry, "ts": datetime.datetime.now().isoformat(), "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def on_idle_tick(self) -> None:
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

    def _handle_output(self, chunk: bytes) -> None:
        text = chunk.decode("utf-8", errors="replace")
        clean = self._ansi_strip(text)
        if self._handoff_in_progress and "HANDOFF_COMPLETE" in clean:
            if self._handoff_event is not None:
                self._handoff_event.set()
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

        if not self._injecting and "/handoff" in text:
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

            lp = pathlib.Path.cwd() / ".agentflow" / "verbosity_log.jsonl"
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
        if not self._manual_handoff and not self._handoff_in_progress and _since_restart >= _restart_cooldown:
            primary = self._config["handoff_primary_tokens"]
            safety = self._config["handoff_safety_tokens"]
            ceiling = self._config["handoff_hard_ceiling_tokens"]
            self._log_audit({"event": "token_evaluation", "accumulated_tokens": total, "primary": primary, "safety": safety, "ceiling": ceiling})
            triggered = False

            # Primary: 80K + a scheduled task just completed (no task in-flight)
            task_just_completed = complete_m is not None
            if not triggered and total >= primary and task_just_completed and not self._task_start_tokens:
                self.trigger_handoff(trigger="auto-primary")
                triggered = True

            # Safety net: 120K + no task in-flight
            if not triggered and total >= safety and not self._task_start_tokens:
                self.trigger_handoff(trigger="auto-safety")
                triggered = True

            # Hard ceiling: 150K unconditional
            if not triggered and total >= ceiling:
                self.trigger_handoff(trigger="auto-ceiling")

    def _record_task_tokens(self, task_id: str, delta: int) -> None:
        rp, el, fc = pathlib.Path.cwd() / ".agentflow" / "current_round.json", 0, 0
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
        in_pytest = "PYTEST_CURRENT_TEST" in os.environ
        run_async = not in_pytest or getattr(self, "_force_async_handoff", False)
        self._handoff_in_progress = True
        import threading
        self._handoff_event = threading.Event()
        if run_async:
            self._handoff_thread = threading.Thread(target=self._run_handoff_core, args=(trigger,), daemon=True)
            self._handoff_thread.start()
        else:
            self._run_handoff_core(trigger)

    def _run_handoff_core(self, trigger: str) -> None:
        self._handoff_in_progress = True
        self._log_audit({"event": "trigger_handoff", "trigger": trigger})
        self._injecting = True
        try:
            self._pty.write_input("/handoff\n")
        except OSError:
            self._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": getattr(self, "_last_accumulated_tokens", 0)})
            self._handoff_in_progress = False
            self._injecting = False
            return
        self._injecting = False
        deadline = time.monotonic() + 120
        handoff_complete = False
        while time.monotonic() < deadline:
            if self._handoff_event and self._handoff_event.is_set():
                handoff_complete = True
                break
            if getattr(self._pty, "_exited", False):
                break
            chunk = self._pty.read_output(timeout=0.1)
            if chunk:
                try:
                    os.write(1, chunk)
                except OSError:
                    pass
                text = chunk.decode("utf-8", errors="replace")
                if "HANDOFF_COMPLETE" in text:
                    if self._handoff_event:
                        self._handoff_event.set()
                    handoff_complete = True
                    break
        if not handoff_complete:
            self._log_audit({"event": "handoff_aborted", "trigger": trigger, "tokens": getattr(self, "_last_accumulated_tokens", 0)})
            self._handoff_in_progress = False
            return
        try:
            self._pty.write_input("/clear\n")
        except OSError:
            pass
        countdown(self._config["restart_delay_seconds"], on_complete=self._restart_session)

    def _restart_session(self) -> None:
        self._handoff_in_progress = False
        self._last_restart_ts = time.monotonic()
        self._log_audit({"event": "restart_session"})
        cmd = "oracle" if self.session_type == "oracle" else "orchestrate" if self.session_type == "orchestrator" else None
        if cmd:
            try:
                self._pty.write_input(f"/{cmd}\n")
            except OSError:
                pass

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

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

_DEFAULTS = {"oracle_threshold_tokens": 60000, "orchestrator_threshold_tokens": 30000, "threshold_pct": 0.30, "restart_delay_seconds": 5, "handoff_token_floor_pct": 0.30}
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
        self._current_turn_output_tokens, self._turn_output_history, self._task_start_tokens = 0, [], {}
        self._arm = self._read_arm_file()
        self._cwd_hash = hashlib.sha256(os.getcwd().encode()).hexdigest()
        self._last_idx_injected = None
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

        start_m = re.search(r"AGENTFLOW_TASK_START:([A-Za-z0-9_-]+)", clean)
        if start_m:
            self._task_start_tokens[start_m.group(1)] = total

        complete_m = re.search(r"AGENTFLOW_TASK_COMPLETE:([A-Za-z0-9_-]+)", clean)
        if complete_m:
            tid = complete_m.group(1)
            if tid in self._task_start_tokens:
                self._record_task_tokens(tid, total - self._task_start_tokens.pop(tid))

        if not self._manual_handoff and not self._handoff_in_progress:
            st = self.session_type
            thresh = self._config["oracle_threshold_tokens" if st == "oracle" else "orchestrator_threshold_tokens"]
            floor = thresh * self._config.get("handoff_token_floor_pct", 0.30)
            self._log_audit({"event": "token_evaluation", "accumulated_tokens": total, "threshold": thresh, "floor": floor})
            triggered = False
            if "AGENTFLOW_ROUND_COMPLETE" in text:
                rp = pathlib.Path.cwd() / ".agentflow" / "current_round.json"
                try:
                    d = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
                    if d.get("closed") or d.get("status") == "closed":
                        if total >= floor:
                            self._handoff_in_progress = True
                            self.trigger_handoff(trigger="auto")
                            self._handoff_in_progress = False
                            triggered = True
                        else:
                            lp = pathlib.Path.cwd() / ".agentflow" / "verbosity_log.jsonl"
                            if lp.parent.exists():
                                entry = {"ts": datetime.datetime.now().isoformat(), "event": "round-complete-low-tokens", "session_type": st, "accumulated_tokens": total, "floor": floor, "session_id": os.environ.get("AGENTFLOW_SESSION_ID")}
                                with open(lp, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(entry) + "\n")
                            rp.unlink(missing_ok=True)
                except Exception:
                    pass
            if not triggered and (total > thresh or total > thresh * self._config["threshold_pct"]):
                self._handoff_in_progress = True
                self.trigger_handoff(trigger="auto")
                self._handoff_in_progress = False

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
        self._log_audit({"event": "trigger_handoff", "trigger": trigger})
        self._injecting = True
        self._pty.write_input("/handoff\n")
        self._injecting = False
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            chunk = self._pty.read_output(timeout=1.0)
            text = chunk.decode("utf-8", errors="replace") if chunk else ""
            if "HANDOFF_COMPLETE" in text:
                break
        self._pty.write_input("/clear\n")
        countdown(self._config["restart_delay_seconds"], on_complete=self._restart_session)

    def _restart_session(self) -> None:
        self._log_audit({"event": "restart_session"})
        cmd = "oracle" if self.session_type == "oracle" else "orchestrate" if self.session_type == "orchestrator" else None
        if cmd:
            self._pty.write_input(f"/{cmd}\n")

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

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
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from agentflow.shell.countdown import countdown

_DEFAULTS = {"oracle_threshold_tokens": 60000, "orchestrator_threshold_tokens": 30000, "threshold_pct": 0.30, "restart_delay_seconds": 5, "handoff_token_floor_pct": 0.30}

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDhJlsu]")
_READ_PATH_RE = re.compile(r"Read\([^)]*?file_path\s*=\s*[\"']([^\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']|Read\([\"']([^\s\"')]+\.(?:py|md|json|toml|yaml|yml|txt))[\"']\)|(?:^|\b)Read\s+tool\s+[\"']?([^\s\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']?", re.MULTILINE)

class SessionManager:
    """Monitors PTY I/O; injects IDX banners and triggers handoff on threshold."""

    def __init__(self, pty_wrapper, tokenizer, config: dict) -> None:
        cfg = dict(_DEFAULTS)
        if tomllib is not None:
            try:
                with open(pathlib.Path.home() / ".agentflow" / "config.toml", "rb") as fh:
                    cfg.update(tomllib.load(fh).get("shell", {}))
            except Exception:
                pass

        cfg.update(config or {})
        self._config = cfg
        self._pty = pty_wrapper
        self._tokenizer = tokenizer
        self.session_type: Optional[str] = None
        self._turn_count = 0
        self._manual_handoff = self._injecting = self._handoff_in_progress = self._last_had_content = False
        self._current_turn_output_tokens = 0
        self._turn_output_history: list[int] = []
        self._task_start_tokens: dict[str, int] = {}

        cwd = os.getcwd()
        self._cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()
        self._last_idx_injected: str | None = None

        pty_wrapper._on_output = self._handle_output
        pty_wrapper._on_exit = self._on_session_exit

    def on_idle_tick(self) -> None:
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

        if self.session_type is None:
            if "/oracle" in text:
                self.session_type = "oracle"
            elif "/orchestrate" in text:
                self.session_type = "orchestrator"

        if not self._injecting and "/handoff" in text:
            self._manual_handoff = True

        if self._last_had_content and "\n\n" in text:
            self._turn_count += 1
            self._last_had_content = False
            self._turn_output_history.append(self._current_turn_output_tokens)
            if len(self._turn_output_history) > 10:
                self._turn_output_history = self._turn_output_history[-10:]

            # Incremental write of verbosity turn data to verbosity_log.jsonl
            log_path = pathlib.Path.cwd() / ".agentflow" / "verbosity_log.jsonl"
            if log_path.parent.exists():
                try:
                    entry = {
                        "ts": datetime.datetime.now().isoformat(),
                        "session_type": self.session_type,
                        "turn": self._turn_count,
                        "output_tokens": self._current_turn_output_tokens,
                    }
                    with open(log_path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry) + "\n")
                except Exception:
                    pass

            self._current_turn_output_tokens = 0
            self._last_idx_injected = None

        if text.strip():
            self._last_had_content = True

        self._current_turn_output_tokens += self._tokenizer.count_tokens(text, "claude")
        total = self._tokenizer.accumulate(text, "claude")

        # T-067 task bracketing checks
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
            
            triggered = False
            if "AGENTFLOW_ROUND_COMPLETE" in text:
                rp = pathlib.Path.cwd() / ".agentflow" / "current_round.json"
                try:
                    with open(rp, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if d.get("closed") or d.get("status") == "closed":
                        if total >= floor:
                            self._handoff_in_progress = True
                            self.trigger_handoff()
                            self._handoff_in_progress = False
                            triggered = True
                        else:
                            lp = pathlib.Path.cwd() / ".agentflow" / "verbosity_log.jsonl"
                            if lp.parent.exists():
                                with open(lp, "a", encoding="utf-8") as f:
                                    f.write(json.dumps({"ts": datetime.datetime.now().isoformat(), "event": "round-complete-low-tokens", "session_type": st, "accumulated_tokens": total, "floor": floor}) + "\n")
                            rp.unlink(missing_ok=True)
                except Exception:
                    pass
            if not triggered and (total > thresh or total > thresh * self._config["threshold_pct"]):
                self._handoff_in_progress = True
                self.trigger_handoff()
                self._handoff_in_progress = False

    def _record_task_tokens(self, task_id: str, delta: int) -> None:
        rp = pathlib.Path.cwd() / ".agentflow" / "current_round.json"
        el = fc = 0
        if rp.exists():
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    d = json.load(f)
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

    def trigger_handoff(self) -> None:
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
        if self.session_type == "oracle":
            self._pty.write_input("/oracle\n")
        elif self.session_type == "orchestrator":
            self._pty.write_input("/orchestrate\n")

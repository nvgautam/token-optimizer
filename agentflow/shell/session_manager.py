"""PTY session manager — handoff, countdown, idx injection.

Stdlib-only. Zero LLM calls. Fully deterministic.
"""
from __future__ import annotations

import hashlib
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

_DEFAULTS: dict = {
    "oracle_threshold_tokens": 60_000,
    "orchestrator_threshold_tokens": 30_000,
    "threshold_pct": 0.30,
    "restart_delay_seconds": 5,
}

_IDX_BANNER = (
    "[IDX] Before any Read: for each file, check"
    " ~/.agentflow/cache/{hash}/index/<that-file>.idx first"
    " — grep name:start-end, then Read(offset, limit).\n"
)

_VERBOSITY_STATIC_BANNER = "[VERBOSITY] Target <=3 sentences (~150 tokens) per response.\n"

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDhJlsu]")
_READ_PATH_RE = re.compile(
    # keyword-arg form: Read(file_path="...") — actual Claude Code tool display
    r"Read\([^)]*?file_path\s*=\s*[\"']([^\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']"
    # positional form: Read("/path/file.ext")
    r"|Read\([\"']([^\s\"')]+\.(?:py|md|json|toml|yaml|yml|txt))[\"']\)"
    # natural-language form: Read tool path.ext
    r"|(?:^|\b)Read\s+tool\s+[\"']?([^\s\"']+\.(?:py|md|json|toml|yaml|yml|txt))[\"']?",
    re.MULTILINE,
)


class SessionManager:
    """Monitors PTY I/O; injects IDX banners and triggers handoff on threshold."""

    def __init__(self, pty_wrapper, tokenizer, config: dict) -> None:
        cfg: dict = dict(_DEFAULTS)

        # Merge ~/.agentflow/config.toml [shell] section if available
        if tomllib is not None:
            config_path = pathlib.Path.home() / ".agentflow" / "config.toml"
            try:
                with open(config_path, "rb") as fh:
                    toml_data = tomllib.load(fh)
                cfg.update(toml_data.get("shell", {}))
            except Exception:  # noqa: BLE001 — absent or malformed; use defaults
                pass

        cfg.update(config or {})
        self._config = cfg

        self._pty = pty_wrapper
        self._tokenizer = tokenizer

        self.session_type: Optional[str] = None
        self._turn_count: int = 0
        self._manual_handoff: bool = False
        self._injecting: bool = False        # suppress manual-handoff detect while we write
        self._handoff_in_progress: bool = False  # guard against reentrant trigger
        self._last_had_content: bool = False

        self._current_turn_output_tokens: int = 0
        self._turn_output_history: list[int] = []

        cwd = os.getcwd()
        self._cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()
        self._last_idx_injected: str | None = None

        # Register ourselves as the output and exit handlers
        pty_wrapper._on_output = self._handle_output
        pty_wrapper._on_exit = self._on_session_exit

        self._verbosity_last_inject: float = time.monotonic()
        self._initial_banner_sent: bool = False
        self._last_output_time: float = time.monotonic()
        self._pending_banner: str = ""
        self._quiet_period_seconds: float = float(
            cfg.get("startup_quiet_period_seconds", 1.5)
        )

    # ------------------------------------------------------------------
    # Output handler
    # ------------------------------------------------------------------

    def on_idle_tick(self) -> None:
        """Called by the PTY loop each iteration when no PTY output arrives.

        Injects startup banners once the TUI has been quiet long enough to
        guarantee Claude is idle and readline is ready to accept input.
        """
        if self._initial_banner_sent:
            return
        if time.monotonic() - self._last_output_time >= self._quiet_period_seconds:
            self._initial_banner_sent = True
            self._pending_banner += _VERBOSITY_STATIC_BANNER
            self._pending_banner += _IDX_BANNER.format(hash=self._cwd_hash)

    def _handle_output(self, chunk: bytes) -> None:
        text = chunk.decode("utf-8", errors="replace")
        self._last_output_time = time.monotonic()

        # T-052: targeted idx injection — check for Read calls in clean text
        clean = self._ansi_strip(text)
        detected_path = self._detect_read_path(clean)
        if detected_path and detected_path.startswith("/"):
            cwd = os.getcwd() + "/"
            detected_path = detected_path[len(cwd):] if detected_path.startswith(cwd) else None
        if detected_path and detected_path != self._last_idx_injected:
            idx_path = (
                pathlib.Path.home()
                / ".agentflow" / "cache" / self._cwd_hash
                / "index" / (detected_path + ".idx")
            )
            if idx_path.exists():
                self._pending_banner += (
                    f"[IDX] {detected_path}.idx exists"
                    " — use Read(offset=N, limit=M) for targeted reads.\n"
                )
                self._last_idx_injected = detected_path

        # 1. Session-type detection — first occurrence wins
        if self.session_type is None:
            if "/oracle" in text:
                self.session_type = "oracle"
            elif "/orchestrate" in text:
                self.session_type = "orchestrator"

        # 2. Manual /handoff detection (user-initiated, not injected by us)
        if not self._injecting and "/handoff" in text:
            self._manual_handoff = True

        # 3. Turn counter — boundary: \n\n following non-empty content
        if self._last_had_content and "\n\n" in text:
            self._turn_count += 1
            self._last_had_content = False

            # T-010: save per-turn count, check verbosity, reset
            turn_tokens = self._current_turn_output_tokens
            self._turn_output_history.append(turn_tokens)
            if len(self._turn_output_history) > 10:
                self._turn_output_history = self._turn_output_history[-10:]
            self._current_turn_output_tokens = 0
            self._last_idx_injected = None  # reset dedup guard at turn boundary
            if turn_tokens > self._config.get("verbosity_threshold", 800):
                self._inject_verbosity_banner(turn_tokens)

            if self._turn_count % 3 == 0:
                self._inject_idx_banner()

        if text.strip():
            self._last_had_content = True

        # T-010: accumulate chunk tokens into current turn counter
        self._current_turn_output_tokens += self._tokenizer.count_tokens(text, "claude")

        # 4. Tokenizer accumulation + threshold check
        total = self._tokenizer.accumulate(text, "claude")
        if not self._manual_handoff and not self._handoff_in_progress:
            threshold = (
                self._config["oracle_threshold_tokens"]
                if self.session_type == "oracle"
                else self._config["orchestrator_threshold_tokens"]
            )
            window_size = threshold
            threshold_pct = self._config["threshold_pct"]
            if total > threshold or total > window_size * threshold_pct:
                self._handoff_in_progress = True
                self.trigger_handoff()
                self._handoff_in_progress = False

    def _ansi_strip(self, text: str) -> str:
        """Strip ANSI escape sequences; leave plain text unchanged."""
        return _ANSI_ESCAPE_RE.sub("", text)

    def _detect_read_path(self, text: str) -> str | None:
        """Return file path if a Claude Code Read invocation is present; else None."""
        m = _READ_PATH_RE.search(text)
        return next((g for g in m.groups() if g), None) if m else None

    def _inject_idx_banner(self) -> None:
        self._pending_banner += _IDX_BANNER.format(hash=self._cwd_hash)

    def _inject_verbosity_banner(self, n: int) -> None:
        now = time.monotonic()
        if now - self._verbosity_last_inject < 30.0:
            return
        self._pending_banner += (
            f"[VERBOSITY] Last response: {n} tokens"
            " — target ≤3 sentences (~150 tokens) for sparring exchanges.\n"
        )
        self._verbosity_last_inject = now

    def pop_pending_banner(self) -> str:
        """Return accumulated banner text and clear the queue."""
        banner = self._pending_banner
        self._pending_banner = ""
        return banner

    # ------------------------------------------------------------------
    # Session exit
    # ------------------------------------------------------------------

    def _on_session_exit(self, exit_code: int) -> None:  # noqa: ARG002
        import datetime
        import json

        log_path = pathlib.Path.cwd() / ".agentflow" / "verbosity_log.jsonl"
        if not log_path.parent.exists():
            return
        ts = datetime.datetime.now().isoformat()
        with open(log_path, "a", encoding="utf-8") as fh:
            for i, output_tokens in enumerate(self._turn_output_history, start=1):
                fh.write(
                    json.dumps({
                        "ts": ts,
                        "session_type": self.session_type,
                        "turn": i,
                        "output_tokens": output_tokens,
                    }) + "\n"
                )

    # ------------------------------------------------------------------
    # Handoff
    # ------------------------------------------------------------------

    def trigger_handoff(self) -> None:
        """Write /handoff, wait up to 120 s for HANDOFF_COMPLETE, clear, countdown."""
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
        countdown(
            self._config["restart_delay_seconds"],
            on_complete=self._restart_session,
        )

    def _restart_session(self) -> None:
        """Re-invoke the original skill after a successful handoff."""
        if self.session_type == "oracle":
            self._pty.write_input("/oracle\n")
        elif self.session_type == "orchestrator":
            self._pty.write_input("/orchestrate\n")

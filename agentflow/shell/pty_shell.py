"""ProxyShell — lifecycle manager for the AgentFlow HTTP proxy subprocess.

Spawns agentflow.proxy.server as a child process, reads the bound port,
sets ANTHROPIC_BASE_URL so Claude Code hits the proxy, and tears down
cleanly on stop().
"""

from __future__ import annotations

import os
import random
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional


class ProxyShell:
    """Manages the proxy subprocess lifecycle."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
        self._secret: Optional[str] = None
        self.base_url: Optional[str] = None

    def _python_exe(self) -> str:
        """Return the Python executable that has headroom available.

        Prefers sys.executable when it already has headroom. Falls back to
        VIRTUAL_ENV/bin/python, then .venv/bin/python, so the proxy subprocess
        can import headroom even when the CLI entry-point runs under a different
        interpreter (e.g. a global conda install).
        """
        import importlib.util
        if importlib.util.find_spec("headroom") is not None:
            return sys.executable
        # Try the active venv (VIRTUAL_ENV env var), then .venv convention
        for candidate in [
            os.environ.get("VIRTUAL_ENV", ""),
            str(self.project_root / ".venv"),
        ]:
            if candidate:
                exe = Path(candidate) / "bin" / "python"
                if exe.exists():
                    return str(exe)
        return sys.executable

    def _flip_ab_arm(self) -> None:
        arm = "on" if random.random() < 0.5 else "off"
        arm_file = self.project_root / ".agentflow" / "verbosity_ab_arm.txt"
        arm_file.parent.mkdir(parents=True, exist_ok=True)
        arm_file.write_text(arm)

    def _write_model_arm(self) -> None:
        """Write .agentflow/model_ab_arm.txt with 'haiku' or 'sonnet'.

        Reads agentflow_ledger.json to find the last session's model_arm and
        alternates; defaults to 'sonnet' if no prior session is found.
        """
        import json as _json
        arm_file = self.project_root / ".agentflow" / "model_ab_arm.txt"
        arm_file.parent.mkdir(parents=True, exist_ok=True)
        last_arm = "sonnet"
        ledger_path = self.project_root / "agentflow_ledger.json"
        if ledger_path.exists():
            try:
                data = _json.loads(ledger_path.read_text(encoding="utf-8"))
                sessions = data.get("sessions", [])
                if sessions:
                    last_arm = sessions[-1].get("model_arm", "sonnet")
            except Exception:
                pass
        arm = "haiku" if last_arm == "sonnet" else "sonnet"
        arm_file.write_text(arm)

    def start(self) -> None:
        """Spawn proxy subprocess, read port, set ANTHROPIC_BASE_URL env."""
        self._flip_ab_arm()
        self._write_model_arm()
        self._secret = secrets.token_hex(32)
        env = {
            **os.environ,
            "AGENTFLOW_PROXY_SECRET": self._secret,
            "AGENTFLOW_PROJECT_ROOT": str(self.project_root),
        }
        self._proc = subprocess.Popen(
            [self._python_exe(), "-m", "agentflow.proxy.server"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Read the port line printed by server.py on startup.
        # If the process dies before printing (e.g. headroom missing), readline() returns "".
        port_line = self._proc.stdout.readline().strip()  # type: ignore[union-attr]

        if not port_line or self._proc.poll() is not None:
            # Server exited — headroom unavailable or startup error
            self.base_url = None
            return

        try:
            port = int(port_line)
        except ValueError:
            self.base_url = None
            return

        self.base_url = f"http://127.0.0.1:{port}"
        os.environ["ANTHROPIC_BASE_URL"] = self.base_url

    def stop(self) -> None:
        """Terminate proxy subprocess cleanly."""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        # Restore env so subsequent processes don't try to hit a dead proxy.
        os.environ.pop("ANTHROPIC_BASE_URL", None)
        self._proc = None

    def banner(self) -> str:
        """Return a one-line startup status string."""
        if self._proc is not None and self._proc.poll() is None:
            return f"[agentflow] proxy: active ({self.base_url})"
        return "[agentflow] proxy: inactive (headroom not available)"

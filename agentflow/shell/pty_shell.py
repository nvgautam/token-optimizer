"""ProxyShell — lifecycle manager for the AgentFlow HTTP proxy subprocess.

Spawns agentflow.proxy.server as a child process, reads the bound port,
sets ANTHROPIC_BASE_URL so Claude Code hits the proxy, and tears down
cleanly on stop().
"""

from __future__ import annotations

import os
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

    def start(self) -> None:
        """Spawn proxy subprocess, read port, set ANTHROPIC_BASE_URL env."""
        self._secret = secrets.token_hex(32)
        env = {
            **os.environ,
            "AGENTFLOW_PROXY_SECRET": self._secret,
            "AGENTFLOW_PROJECT_ROOT": str(self.project_root),
        }
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "agentflow.proxy.server"],
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

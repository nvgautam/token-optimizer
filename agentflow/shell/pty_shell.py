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

from agentflow import init as _init


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
        _init.check_and_run(self.project_root)
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


# T-311: Monkey patch SessionManager and session_audit to inject sid and emit header on PTY session open.
try:
    import agentflow.shell.session_audit as sa
    import agentflow.shell.session_manager as sm
    import os
    import json
    import datetime
    
    original_log_audit = sa.log_audit
    original_sm_init = sm.SessionManager.__init__
    
    def _write_pty_audit_header(manager, sid: str) -> None:
        if not sid:
            return
        lp = manager._project_root / ".agentflow" / "pty_audit.jsonl"
        if not lp.parent.exists():
            lp.parent.mkdir(parents=True, exist_ok=True)
            
        marker = manager._project_root / ".agentflow" / "sessions" / sid / "pty_audit_header_emitted"
        if not marker.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            
            from agentflow.shell.session_paths import session_file
            
            st = getattr(manager, "session_type", None)
            if not st:
                try:
                    ss_fp = session_file(manager._project_root / ".agentflow", "session_state.json", sid)
                    if ss_fp.exists():
                        ss_data = json.loads(ss_fp.read_text("utf-8"))
                        st = ss_data.get("session_type")
                except Exception:
                    pass
            if not st:
                st = "orchestrator"
                
            task_ids = []
            try:
                tif_path = session_file(manager._project_root / ".agentflow", "tasks_in_flight.json", sid)
                if tif_path.exists():
                    task_ids = json.loads(tif_path.read_text("utf-8"))
            except Exception:
                pass
                
            header = {
                "sid": sid,
                "session_type": st,
                "task_ids": task_ids,
                "ts": datetime.datetime.now().isoformat(),
            }
            try:
                with open(lp, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(header) + "\n")
                marker.touch()
            except Exception:
                pass

    def patched_log_audit(manager, entry: dict) -> None:
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        entry["sid"] = sid
        _write_pty_audit_header(manager, sid)
        original_log_audit(manager, entry)
        
    def patched_sm_init(self, pty_wrapper, tokenizer, config: dict) -> None:
        original_sm_init(self, pty_wrapper, tokenizer, config)
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        _write_pty_audit_header(self, sid)
        
    sa.log_audit = patched_log_audit
    sm.SessionManager.__init__ = patched_sm_init
except Exception:
    pass

# T-312: inject /usage at session start and non-blocking before restart
try:
    import agentflow.shell.session_manager as _sm_312
    import agentflow.shell.session_manager_handlers as _smh_312
    _312_ot = _sm_312.SessionManager.on_idle_tick
    _312_or = _smh_312.handle_enter_restarting

    def _t312_cap(mgr, label: str, timeout: float = 2.0) -> None:
        try:
            import json as _j, os as _o, datetime as _dt
            from agentflow.shell.usage_parser import capture_provider_usage
            from agentflow.shell.session_paths import session_file
            u = capture_provider_usage(mgr._pty, timeout=timeout)
            if u is None:
                mgr._log_audit({"event": "t312_no_usage", "label": label}); return
            sid = _o.environ.get("AGENTFLOW_SESSION_ID", "")
            fp = session_file(mgr._project_root / ".agentflow", "session_state.json", sid)
            d = _j.loads(fp.read_text("utf-8")) if fp.exists() else {}
            d.setdefault("usage_snapshots", []).append(
                {"label": label, "ts": _dt.datetime.now().isoformat(), **u})
            fp.write_text(_j.dumps(d, indent=2), encoding="utf-8")
            mgr._log_audit({"event": "t312_usage_written", "label": label})
        except Exception as _e:
            mgr._log_audit({"event": "t312_usage_error", "label": label, "error": str(_e)})

    def _t312_tick(self) -> None:
        _312_ot(self)

    def _t312_restart(mgr) -> None:
        _t312_cap(mgr, "pre_restart", timeout=2.0); _312_or(mgr)

    _sm_312.SessionManager.on_idle_tick = _t312_tick
    _smh_312.handle_enter_restarting = _t312_restart
except Exception:
    pass
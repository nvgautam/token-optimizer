#!/usr/bin/env python3
"""UserPromptSubmit hook: clear signal files on /orchestrate and /handoff."""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file
from agentflow.hooks.ups_task_sync import _cleanup_merged_in_flight, _log_drain


def _write_session_state_atomic(agentflow_dir: Path, session_type: str, sid: str = "") -> None:
    """Write session_state.json to sessions/<sid>/ if sid, else to root."""
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        session_state_file = session_file(agentflow_dir, "session_state.json", sid)
        data = {"session_type": session_type}
        with tempfile.NamedTemporaryFile(
            mode="w", dir=session_state_file.parent, delete=False, suffix=".tmp", encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, session_state_file)
        _log_drain(agentflow_dir, {"event": "session_state_written", "session_type": session_type, "sid": sid})
    except Exception as e:
        _log_drain(agentflow_dir, {"event": "write_session_state_error", "error": str(e)})


def main() -> None:
    prompt = None

    # Read the prompt from standard input JSON context if not a TTY
    if not sys.stdin.isatty():
        try:
            data = json.load(sys.stdin)
            if isinstance(data, dict):
                prompt = data.get("prompt")
        except (json.JSONDecodeError, Exception) as e:
            print(json.dumps({"hook": "user_prompt_submit.py", "event": "read_prompt_error", "error": str(e), "ts": time.time()}), file=sys.stderr)

    # If not found or stdin is not a TTY/empty, fallback to sys.argv[1:]
    if prompt is None:
        prompt = " ".join(sys.argv[1:])

    # Locate the project .agentflow directory
    project_root = os.environ.get("AGENTFLOW_PROJECT_ROOT", "")
    if project_root:
        agentflow_dir = Path(project_root) / ".agentflow"
    else:
        agentflow_dir = Path.cwd() / ".agentflow"

    # T-329: Parse namespace and subcommand from the leading slash command.
    # Uses exact name matching to avoid false-positives from skills whose names
    # merely contain "orchestrat" (e.g. /my-orchestrator-tool — T-292 / T-329).
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    is_orchestrate = is_oracle = is_handoff = False
    if prompt:
        m = re.match(r"\s*/(\S+)", prompt)
        if m:
            cmd = m.group(1)                         # e.g. "claude:orchestrate"
            ns, _, sub = cmd.partition(":")          # ns="claude", sub="orchestrate"
            is_orchestrate = sub == "orchestrate" or ns in ("orchestrate", "orchestrator")
            is_oracle      = sub == "oracle"      or ns == "oracle"
            is_handoff     = sub == "handoff"     or ns == "handoff"

    if prompt:
        if is_orchestrate:
            _write_session_state_atomic(agentflow_dir, "orchestrator", sid=sid)
        elif is_oracle:
            _write_session_state_atomic(agentflow_dir, "oracle", sid=sid)

    # If the prompt starts with /orchestrate or /handoff (bare or namespaced):
    if prompt and (is_orchestrate or is_handoff):
        # Delete session-scoped handoff_complete and task_complete if they exist.
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        for name in ("handoff_complete.json", "task_complete.json"):
            complete_file = session_file(agentflow_dir, name, sid)
            try:
                if complete_file.exists():
                    complete_file.unlink()
                    _log_drain(agentflow_dir, {"event": "signal_file_unlinked", "file": name})
            except Exception as e:
                _log_drain(agentflow_dir, {"event": "delete_signal_file_error", "error": str(e), "file": complete_file.name})


    # If the prompt is exactly "/clear" (slash command, not prose), write the clear signal file
    if prompt and prompt.strip() == "/clear":
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        clear_signal_file = agentflow_dir / "clear_signal"
        try:
            clear_signal_file.touch(exist_ok=True)
        except Exception as e:
            _log_drain(agentflow_dir, {"event": "touch_clear_signal_error", "error": str(e)})

    # Clean up merged in-flight tasks
    _cleanup_merged_in_flight(agentflow_dir, sid=sid)

    # Emit session type into every turn so skills never need to infer it.
    try:
        session_type = "unknown"
        ss = session_file(agentflow_dir, "session_state.json", sid)
        if ss.exists():
            st = json.loads(ss.read_text())
            session_type = st.get("session_type") or "unknown"
        print(f"<agentflow-reminder>[SESSION: {session_type}]</agentflow-reminder>")

        # Oracle consent check: update context_fill.json timestamp if it exists,
        # then check should_prompt_consent. If it is True, we touch/update context_fill.json ts
        # so that the PTY session manager will also see it as fresh and fire the prompt!
        if session_type == "oracle":
            fill_path = session_file(agentflow_dir, "context_fill.json", sid)
            if fill_path.exists():
                try:
                    data = json.loads(fill_path.read_text("utf-8"))
                    data["ts"] = time.time()
                    with tempfile.NamedTemporaryFile(
                        mode="w", dir=fill_path.parent, delete=False, suffix=".tmp", encoding="utf-8"
                    ) as tmp:
                        json.dump(data, tmp)
                        tmp_path = Path(tmp.name)
                    os.replace(tmp_path, fill_path)
                except Exception:
                    pass

            from agentflow.shell.oracle_consent import should_prompt_consent, inject_consent_prompt
            from agentflow.shell.state_machine import States

            class HookConsentManager:
                def __init__(self, root_dir: Path, s_type: str):
                    self._project_root = root_dir
                    self.session_type = s_type
                    
                    class FakeSM:
                        state = States.IDLE
                    self._state_machine = FakeSM()
                    
                    self._config = {
                        "oracle_threshold_tokens": 50000,
                    }
                    try:
                        import tomllib
                    except ImportError:
                        import tomli as tomllib
                    try:
                        cfg_path = Path.home() / ".agentflow" / "config.toml"
                        if cfg_path.exists():
                            with open(cfg_path, "rb") as fh:
                                toml_cfg = tomllib.load(fh)
                                self._config.update(toml_cfg.get("shell", {}))
                    except Exception:
                        pass
                    
                    if "oracle_consent_threshold_tokens" not in self._config:
                        self._config["oracle_consent_threshold_tokens"] = self._config["oracle_threshold_tokens"]
                        
                    self._oracle_consent_fired = False
                    self._oracle_consent_pending = False
                    self._last_accumulated_tokens = 0
                    
                    class MockPty:
                        def write_input(self, text: str) -> None:
                            pass
                    self._pty = MockPty()
                    
                def _auto_handoff_disabled(self) -> bool:
                    return (self._project_root / ".agentflow" / "handoff_disabled").exists()
                
                def _log_audit(self, entry: dict) -> None:
                    pass

            mock_manager = HookConsentManager(agentflow_dir.parent, session_type)
            if should_prompt_consent(mock_manager):
                inject_consent_prompt(mock_manager)
    except Exception as e:
        print(json.dumps({"hook": "user_prompt_submit.py", "event": "session_type_error", "error": str(e), "ts": time.time()}), file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()

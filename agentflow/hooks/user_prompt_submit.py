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
from agentflow.config import constants


def _write_session_state_atomic(agentflow_dir: Path, session_type: str, sid: str = "") -> None:
    """Write session_state.json to sessions/<sid>/ if sid, else to root."""
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        session_state_file = session_file(agentflow_dir, constants.FILE_SESSION_STATE, sid)
        data = {constants.KEY_SESSION_TYPE: session_type}
        with tempfile.NamedTemporaryFile(
            mode="w", dir=session_state_file.parent, delete=False, suffix=".tmp", encoding=constants.UTF8
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, session_state_file)
        _log_drain(agentflow_dir, {constants.HOOK_FIELD_EVENT: "session_state_written", constants.KEY_SESSION_TYPE: session_type, constants.KEY_SID: sid})
    except Exception as e:
        _log_drain(agentflow_dir, {constants.HOOK_FIELD_EVENT: "write_session_state_error", constants.HOOK_FIELD_ERROR: str(e)})


def _get_session_token_count(agentflow_dir: Path, sid: str = "") -> int:
    """Get current session accumulated token count from context_fill.json."""
    try:
        context_fill_file = session_file(agentflow_dir, constants.FILE_CONTEXT_FILL, sid)
        if context_fill_file.exists():
            data = json.loads(context_fill_file.read_text(constants.UTF8))
            return data.get("fill_tokens", 0)
    except Exception:
        pass
    return 0


def _read_and_decrement_snooze(agentflow_dir: Path, sid: str = "") -> int:
    """Read snooze file and decrement count. Return remaining count or -1 if file not found."""
    try:
        session_dir = session_file(agentflow_dir, "dummy", sid).parent if sid else agentflow_dir
        snooze_file = session_dir / "restart_snooze"
        if snooze_file.exists():
            count = int(snooze_file.read_text(constants.UTF8).strip())
            if count <= 0:
                snooze_file.unlink()
                return -1
            new_count = count - 1
            if new_count <= 0:
                snooze_file.unlink()
            else:
                snooze_file.write_text(str(new_count), encoding=constants.UTF8)
            return new_count
    except Exception:
        pass
    return -1


def _inject_restart_consent_prompt() -> None:
    """Inject restart consent question into the prompt context."""
    consent_prompt = (
        "\n<agentflow-restart-consent>\n"
        "**Session context approaching limit.** Would you like to continue in this session or start fresh?\n"
        "Reply with:\n"
        "- **Continue** to keep working here (snooze for 3 more turns)\n"
        "- **Yes handoff and restart** to flush state and restart\n"
        "</agentflow-restart-consent>\n"
    )
    print(consent_prompt)


def main() -> None:
    prompt = None

    # Read the prompt from standard input JSON context if not a TTY
    if not sys.stdin.isatty():
        try:
            data = json.load(sys.stdin)
            if isinstance(data, dict):
                prompt = data.get(constants.KEY_PROMPT)
        except (json.JSONDecodeError, Exception) as e:
            print(json.dumps({constants.HOOK_FIELD_HOOK: constants.HOOK_USER_PROMPT_SUBMIT, constants.HOOK_FIELD_EVENT: "read_prompt_error", constants.HOOK_FIELD_ERROR: str(e), constants.HOOK_FIELD_TS: time.time()}), file=sys.stderr)

    # If not found or stdin is not a TTY/empty, fallback to sys.argv[1:]
    if prompt is None:
        prompt = " ".join(sys.argv[1:])

    # Locate the project .agentflow directory
    project_root = os.environ.get(constants.ENV_PROJECT_ROOT, "")
    if project_root:
        agentflow_dir = Path(project_root) / constants.DIR_AGENTFLOW
    else:
        agentflow_dir = Path.cwd() / constants.DIR_AGENTFLOW

    # T-329: Parse namespace and subcommand from the leading slash command.
    # Uses exact name matching to avoid false-positives from skills whose names
    # merely contain "orchestrat" (e.g. /my-orchestrator-tool — T-292 / T-329).
    sid = os.environ.get(constants.ENV_SESSION_ID, "")
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
            _write_session_state_atomic(agentflow_dir, constants.SESSION_TYPE_ORCHESTRATOR, sid=sid)
        elif is_oracle:
            _write_session_state_atomic(agentflow_dir, constants.SESSION_TYPE_ORACLE, sid=sid)

    # If the prompt starts with /orchestrate or /handoff (bare or namespaced):
    if prompt and (is_orchestrate or is_handoff):
        # Delete session-scoped handoff_complete and task_complete if they exist.
        # task_complete.json is no longer written (poll_session watches tif==[] now),
        # but retain cleanup here in case a stale file exists from a prior session.
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        for name in (constants.FILE_HANDOFF_COMPLETE, constants.FILE_TASK_COMPLETE):
            complete_file = session_file(agentflow_dir, name, sid)
            try:
                if complete_file.exists():
                    complete_file.unlink()
                    _log_drain(agentflow_dir, {constants.HOOK_FIELD_EVENT: "signal_file_unlinked", "file": name})
            except Exception as e:
                _log_drain(agentflow_dir, {constants.HOOK_FIELD_EVENT: "delete_signal_file_error", constants.HOOK_FIELD_ERROR: str(e), "file": complete_file.name})


    # If the prompt is exactly "/clear" (slash command, not prose), write the clear signal file
    if prompt and prompt.strip() == "/clear":
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        clear_signal_file = agentflow_dir / constants.FILE_CLEAR_SIGNAL
        try:
            clear_signal_file.touch(exist_ok=True)
        except Exception as e:
            _log_drain(agentflow_dir, {constants.HOOK_FIELD_EVENT: "touch_clear_signal_error", constants.HOOK_FIELD_ERROR: str(e)})

    # Clean up merged in-flight tasks
    _cleanup_merged_in_flight(agentflow_dir, sid=sid)

    # Emit session type into every turn so skills never need to infer it.
    try:
        session_type = constants.SESSION_TYPE_UNKNOWN
        ss = session_file(agentflow_dir, constants.FILE_SESSION_STATE, sid)
        if ss.exists():
            st = json.loads(ss.read_text())
            session_type = st.get(constants.KEY_SESSION_TYPE) or constants.SESSION_TYPE_UNKNOWN
        print(f"<agentflow-reminder>[SESSION: {session_type}]</agentflow-reminder>")

        # Oracle consent check: update context_fill.json timestamp if it exists,
        # then check should_prompt_consent. If it is True, we touch/update context_fill.json ts
        # so that the PTY session manager will also see it as fresh and fire the prompt!
        if session_type == constants.SESSION_TYPE_ORACLE:
            fill_path = session_file(agentflow_dir, constants.FILE_CONTEXT_FILL, sid)
            if fill_path.exists():
                try:
                    data = json.loads(fill_path.read_text(constants.UTF8))
                    data[constants.KEY_TS] = time.time()
                    with tempfile.NamedTemporaryFile(
                        mode="w", dir=fill_path.parent, delete=False, suffix=".tmp", encoding=constants.UTF8
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
                        constants.CFG_ORACLE_THRESHOLD_TOKENS: 50000,
                    }
                    try:
                        import tomllib
                    except ImportError:
                        import tomli as tomllib
                    try:
                        cfg_path = Path.home() / constants.DIR_AGENTFLOW / constants.FILE_CONFIG_TOML
                        if cfg_path.exists():
                            with open(cfg_path, "rb") as fh:
                                tz_cfg = tomllib.load(fh)
                                self._config.update(tz_cfg.get(constants.CFG_SHELL, {}))
                    except Exception:
                        pass
                    
                    if constants.CFG_ORACLE_CONSENT_THRESHOLD_TOKENS not in self._config:
                        self._config[constants.CFG_ORACLE_CONSENT_THRESHOLD_TOKENS] = self._config[constants.CFG_ORACLE_THRESHOLD_TOKENS]
                        
                    self._oracle_consent_fired = False
                    self._oracle_consent_pending = False
                    self._last_accumulated_tokens = 0
                    
                    class MockPty:
                        def write_input(self, text: str) -> None:
                            pass
                    self._pty = MockPty()
                    
                def _auto_handoff_disabled(self) -> bool:
                    return (self._project_root / constants.DIR_AGENTFLOW / constants.FILE_HANDOFF_DISABLED).exists()
                
                def _log_audit(self, entry: dict) -> None:
                    pass

            mock_manager = HookConsentManager(agentflow_dir.parent, session_type)
            if should_prompt_consent(mock_manager):
                inject_consent_prompt(mock_manager)
    except Exception as e:
        print(json.dumps({constants.HOOK_FIELD_HOOK: constants.HOOK_USER_PROMPT_SUBMIT, constants.HOOK_FIELD_EVENT: "session_type_error", constants.HOOK_FIELD_ERROR: str(e), constants.HOOK_FIELD_TS: time.time()}), file=sys.stderr)

    # T-357: Check for restart consent when tokens exceed threshold (oracle sessions only)
    try:
        if prompt and session_type == constants.SESSION_TYPE_ORACLE:
            token_count = _get_session_token_count(agentflow_dir, sid)
            if token_count > constants.RESTART_CONSENT_THRESHOLD_TOKENS:
                snooze_count = _read_and_decrement_snooze(agentflow_dir, sid)
                if snooze_count == -1:  # No snooze file exists, inject consent
                    _inject_restart_consent_prompt()
    except Exception as e:
        _log_drain(agentflow_dir, {constants.HOOK_FIELD_EVENT: "restart_consent_error", constants.HOOK_FIELD_ERROR: str(e)})

    sys.exit(0)


if __name__ == "__main__":
    main()

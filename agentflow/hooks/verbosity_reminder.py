#!/usr/bin/env python3
"""UserPromptSubmit hook: verbosity reminder + session type detection."""
import os, sys, json, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file

INTERVAL = 2
COUNTER_FILE = Path.home() / ".agentflow" / "verbosity_turn_counter"
_DISABLED_VALUES = {"1", "true", "yes", "on"}

def _hook_disabled() -> bool:
    return os.environ.get("AGENTFLOW_VERBOSITY_HOOK_DISABLED", "").strip().lower() in _DISABLED_VALUES

def _arm_suppressed() -> bool:
    """A/B arm file says 'off' (suppress reminder)."""
    project_root = os.environ.get("AGENTFLOW_PROJECT_ROOT", "")
    candidates = ([Path(project_root) / ".agentflow" / "verbosity_ab_arm.txt"] if project_root else []) + [Path.home() / ".agentflow" / "verbosity_ab_arm.txt"]
    for path in candidates:
        if path.exists() and path.read_text().strip() == "off":
            return True
    return False

def _read_prompt_from_stdin() -> str | None:
    """Read prompt from stdin JSON."""
    if sys.stdin.isatty():
        return None
    try:
        data = json.load(sys.stdin)
        return data.get("prompt") if isinstance(data, dict) else None
    except Exception as e:
        print(json.dumps({"hook": "verbosity_reminder.py", "event": "read_prompt_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        return None

def _write_session_state_atomic(agentflow_dir: Path, session_type: str, sid: str = "") -> None:
    """Write session_state.json to sessions/<sid>/ if sid, else to root."""
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        session_state_file = session_file(agentflow_dir, "session_state.json", sid)
        with tempfile.NamedTemporaryFile(mode="w", dir=session_state_file.parent, delete=False, suffix=".tmp", encoding="utf-8") as tmp:
            json.dump({"session_type": session_type}, tmp)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, session_state_file)
        print(json.dumps({"hook": "verbosity_reminder.py", "event": "session_state_written", "session_type": session_type, "sid": sid, "ts": time.time()}), file=sys.stderr)
    except Exception as e:
        print(json.dumps({"hook": "verbosity_reminder.py", "event": "write_session_state_error", "error": str(e), "ts": time.time()}), file=sys.stderr)

def main() -> None:
    prompt = _read_prompt_from_stdin()
    if prompt:
        project_root = os.environ.get("AGENTFLOW_PROJECT_ROOT", "")
        agentflow_dir = Path(project_root) / ".agentflow" if project_root else Path.cwd() / ".agentflow"
        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        if "/orchestrate" in prompt:
            _write_session_state_atomic(agentflow_dir, "orchestrator", sid=sid)
        elif "/oracle" in prompt:
            _write_session_state_atomic(agentflow_dir, "oracle", sid=sid)
    if _hook_disabled() or _arm_suppressed():
        sys.exit(0)
    try:
        count = int(COUNTER_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        count = 0
    count += 1
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(str(count))
    if count % INTERVAL == 0:
        print("<agentflow-reminder>[VERBOSITY] Keep responses concise (≤ 3 sentences / ~150 tokens).</agentflow-reminder>")
    sys.exit(0)

if __name__ == "__main__":
    main()

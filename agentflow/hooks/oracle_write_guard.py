"""Write/Edit prevention hook for Oracle sessions.

Blocks Write and Edit tool calls when session_type is 'oracle' and target file
is not in the default or custom allowlist. Prints risk warning on block.
"""

import json
import os
import sys
from pathlib import Path

# Default allowlist of files Oracle can write to
DEFAULT_ALLOWLIST = {
    "design_status.md",
    "architecture.md",
    "execution_plan.md",
    "tasks.json",
}


def _find_workspace_root() -> Path:
    """Find the project root by looking for .agentflow directory."""
    cwd = Path.cwd()
    current = cwd
    while current != current.parent:
        if (current / ".agentflow").exists():
            return current
        current = current.parent
    return cwd


def _get_session_type() -> str:
    """Read session_type from session_state.json if it exists."""
    root = _find_workspace_root()
    agentflow_dir = root / ".agentflow"

    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    if sid:
        session_state_file = agentflow_dir / "sessions" / sid / "session_state.json"
    else:
        session_state_file = agentflow_dir / "session_state.json"

    if not session_state_file.exists():
        return ""

    try:
        data = json.loads(session_state_file.read_text())
        return data.get("session_type", "")
    except Exception:
        return ""


def _get_custom_allowlist() -> set[str]:
    """Load custom allowlist from .agentflow/oracle_allowlist.json if it exists."""
    root = _find_workspace_root()
    allowlist_file = root / ".agentflow" / "oracle_allowlist.json"

    if not allowlist_file.exists():
        return set()

    try:
        data = json.loads(allowlist_file.read_text())
        if isinstance(data, list):
            return set(data)
    except Exception:
        pass

    return set()


def _is_file_allowed(file_path: str) -> bool:
    """Check if file_path is in the default or custom allowlist."""
    try:
        file_path_obj = Path(file_path)
        file_name = file_path_obj.name

        # Check default allowlist
        if file_name in DEFAULT_ALLOWLIST:
            return True

        # Check custom allowlist
        custom_list = _get_custom_allowlist()
        if file_name in custom_list:
            return True

        # Also check relative path from project root
        root = _find_workspace_root()
        try:
            rel_path = file_path_obj.relative_to(root)
            if str(rel_path) in DEFAULT_ALLOWLIST or str(rel_path) in custom_list:
                return True
        except ValueError:
            pass

        return False
    except Exception:
        return False


def _print_risk_warning(file_path: str) -> None:
    """Print risk warning to stderr when write is blocked."""
    warning = f"""
RISK WARNING: Oracle session cannot write to {file_path}

This restriction prevents accidental modifications to implementation files.
To allow writing to this file in Oracle sessions:

1. Create .agentflow/oracle_allowlist.json in project root:
   {{"allowlist": ["path/to/file.py"]}}

2. Or contact your project administrator to update the default allowlist.
""".strip()
    print(warning, file=sys.stderr)


def main() -> None:
    """Check if Write/Edit to file is allowed in current session."""
    try:
        hook_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = hook_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    tool_input = hook_data.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        sys.exit(0)

    session_type = _get_session_type()
    if session_type != "oracle":
        sys.exit(0)

    if _is_file_allowed(file_path):
        sys.exit(0)

    _print_risk_warning(file_path)
    sys.exit(1)


if __name__ == "__main__":
    main()

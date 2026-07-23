"""Stop hook: clear session-scoped agent_active.json when agent turn completes.

Superseded by post_tool_use.py for context capture, but used for prompt-activity tracking.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

FILL_STALE_SECONDS = 60


def main() -> None:
    # Resolve project root and agentflow directory
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    agentflow_dir = project_root / ".agentflow"
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")

    # Clean up active prompt file
    if sid:
        try:
            sys.path.insert(0, str(project_root))
            from agentflow.shell.session_paths import session_file
            active_file = session_file(agentflow_dir, "agent_active.json", sid)
            if active_file.exists():
                active_file.unlink()
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()

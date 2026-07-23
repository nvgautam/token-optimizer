"""Stop hook: clean up agent_active.json when the Claude session ends.

Invoked by the Stop event hook in settings.json.  Removes agent_active.json
so drain_restart knows the session is truly idle.  Exits 0 to allow stop.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.config import constants
from agentflow.shell.session_paths import session_file

FILL_STALE_SECONDS = 60


def main() -> None:
    try:
        project_root = Path(os.environ.get(constants.ENV_PROJECT_ROOT, Path.cwd()))
        agentflow_dir = project_root / constants.DIR_AGENTFLOW
        sid = os.environ.get(constants.ENV_SESSION_ID, "")
        aa_path = session_file(agentflow_dir, constants.FILE_AGENT_ACTIVE, sid if sid else None)
        try:
            aa_path.unlink(missing_ok=True)
        except OSError:
            pass
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()

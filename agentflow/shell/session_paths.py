from pathlib import Path


def session_file(agentflow_dir: Path, filename: str, sid: str | None = None) -> Path:
    """Return the path for a per-SID volatile state file.

    If SID is provided (non-empty string):
    - Creates agentflow_dir/sessions/<sid>/ directory (parents=True, exist_ok=True)
    - Returns agentflow_dir/sessions/<sid>/<filename>

    If SID is None or empty string (legacy fallback):
    - Returns agentflow_dir/<filename>
    """
    # Treat empty string as no SID (legacy fallback)
    if sid:
        sessions_dir = agentflow_dir / "sessions" / sid
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir / filename
    else:
        return agentflow_dir / filename

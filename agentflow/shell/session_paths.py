from __future__ import annotations
from pathlib import Path
import shutil
import time


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


def cleanup_stale_sessions(agentflow_dir: Path, ttl_seconds: int = 86400) -> None:
    """Remove session folders older than ttl_seconds (default 24h).

    Enumerates agentflow_dir/sessions/ subdirectories and removes any whose
    mtime is older than ttl_seconds seconds. Uses shutil.rmtree with
    ignore_errors=True to silently skip any removal failures. If
    agentflow_dir/sessions/ does not exist, returns without error.

    Args:
        agentflow_dir: Path to .agentflow directory
        ttl_seconds: Time-to-live in seconds (default 86400 = 24 hours)
    """
    sessions_dir = agentflow_dir / "sessions"

    # If sessions dir doesn't exist, no-op
    if not sessions_dir.exists():
        return

    current_time = time.time()

    for folder in sessions_dir.iterdir():
        if not folder.is_dir():
            continue
        try:
            folder_mtime = folder.stat().st_mtime
        except OSError:
            continue
        if current_time - folder_mtime > ttl_seconds:
            shutil.rmtree(folder, ignore_errors=True)

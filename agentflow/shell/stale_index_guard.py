"""Stale index guard logic extracted from session_manager."""
from __future__ import annotations
import os
import hashlib
import pathlib
import subprocess
import sys

def run_stale_index_guard() -> None:
    try:
        root = pathlib.Path.cwd().resolve()
        h = hashlib.sha256(str(root).encode()).hexdigest()
        cd = pathlib.Path("~/.agentflow/cache").expanduser().resolve() / h / "index"
        files = []
        if cd.exists():
            for r, _, fs in os.walk(cd):
                for f in fs:
                    if f.endswith(".idx"):
                        ip = pathlib.Path(r) / f
                        sp = root / str(ip.relative_to(cd))[:-4]
                        if sp.exists() and sp.stat().st_mtime > ip.stat().st_mtime:
                            files.append(str(sp))
        for r, ds, fs in os.walk(root):
            ds[:] = [d for d in ds if d not in {".git", ".venv", "node_modules", "__pycache__", ".agentflow", ".pytest_cache"}]
            for f in fs:
                sp = pathlib.Path(r) / f
                if sp.suffix in (".py", ".md"):
                    ip = cd / sp.relative_to(root).parent / f"{f}.idx"
                    if not ip.exists():
                        try:
                            with open(sp, "r", encoding="utf-8", errors="ignore") as fh:
                                if len([fh.readline() for _ in range(50)]) >= 50:
                                    files.append(str(sp))
                        except Exception:
                            pass
        files = list(set(files))
        if files:
            subprocess.run([sys.executable, str(pathlib.Path(__file__).parent.parent / "hooks" / "write_indexer.py")] + files, capture_output=True)
    except Exception:
        pass

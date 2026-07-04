#!/usr/bin/env python3
"""Retrospective bootstrap: detect file split events from git history (T-096).

Usage: python agentflow/reporting/code_size_bootstrap.py
Walks git log of cwd, writes .agentflow/file_families.jsonl.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> str:
    """Run command (no shell=True), return stdout or '' on failure."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def _get_commits(cwd: Path) -> list[tuple[str, str]]:
    """Return list of (sha, iso_ts) for all non-merge commits."""
    out = _run(["git", "log", "--format=%H %aI", "--no-merges"], cwd)
    commits = []
    for line in out.splitlines():
        line = line.strip()
        if " " in line:
            sha, ts = line.split(" ", 1)
            commits.append((sha, ts.strip()))
    return commits


def _get_changed_py_files(sha: str, cwd: Path) -> tuple[list[str], list[str]]:
    """Return (modified_py, added_py) .py filenames for a commit."""
    out = _run(
        ["git", "diff-tree", "--no-commit-id", "-r", "--name-status", "--diff-filter=AM", sha],
        cwd,
    )
    modified: list[str] = []
    added: list[str] = []
    for line in out.splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if not path.endswith(".py"):
            continue
        if status == "M":
            modified.append(path)
        elif status == "A":
            added.append(path)
    return modified, added


def _line_count_at(sha: str, filepath: str, cwd: Path) -> int:
    """Return line count of filepath at commit sha."""
    out = _run(["git", "show", f"{sha}:{filepath}"], cwd)
    return len(out.splitlines())


def _parent_sha(sha: str, cwd: Path) -> str:
    """Return parent commit SHA, or '' for root commits."""
    return _run(["git", "rev-parse", f"{sha}^"], cwd).strip()


def detect_split_events(cwd: Path) -> list[dict]:
    """Walk git history; return list of split-event dicts."""
    events: list[dict] = []
    for sha, ts in _get_commits(cwd):
        modified, added = _get_changed_py_files(sha, cwd)
        if not modified or not added:
            continue
        parent = _parent_sha(sha, cwd)
        if not parent:
            continue
        for mod_file in modified:
            before = _line_count_at(parent, mod_file, cwd)
            if before == 0:
                continue
            after = _line_count_at(sha, mod_file, cwd)
            if after > before * 0.5:  # not shrank ≥50%
                continue
            mod_dir = str(Path(mod_file).parent)
            if mod_dir == ".":
                siblings = added[:]  # root-level file: all added .py files are siblings
            else:
                siblings = [a for a in added if str(Path(a).parent).startswith(mod_dir)]
            if siblings:
                events.append({"parent": mod_file, "children": siblings, "ts": ts})
    return events


def bootstrap(cwd: Path | None = None, families_path: Path | None = None) -> int:
    """Walk git history and append new split families to file_families.jsonl."""
    if cwd is None:
        cwd = Path.cwd()
    if families_path is None:
        families_path = cwd / ".agentflow" / "file_families.jsonl"

    events = detect_split_events(cwd)
    families_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing parents to ensure idempotency
    existing: set[str] = set()
    if families_path.exists():
        try:
            for line in families_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        existing.add(json.loads(line).get("parent", ""))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass

    new_events = [e for e in events if e["parent"] not in existing]
    if new_events:
        with families_path.open("a", encoding="utf-8") as f:
            for e in new_events:
                f.write(json.dumps(e) + "\n")

    print(f"Wrote {len(new_events)} new family entries to {families_path}")
    return 0


if __name__ == "__main__":
    sys.exit(bootstrap())

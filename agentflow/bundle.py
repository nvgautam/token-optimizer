"""Deterministic context bundle assembly for worker/reviewer/test agents.

Reads task metadata from tasks.json, addendum from execution_plan.md, and
the appropriate skill file; writes a JSON bundle to out_dir atomically.
stdlib-only — no LLM calls, no shell=True.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["assemble_bundle"]

# Map agent_type → relative skill file path under project_root
_SKILL_PATHS: dict[str, str] = {
    "worker": "commands/claude/worker/system.md",
    "reviewer": "commands/claude/reviewer/code_review.md",
    "test": "commands/claude/worker/testing_guide.md",
}


def _load_task(tasks_json: Path, task_id: str) -> dict:
    """Return the task entry from tasks.json or raise ValueError."""
    data = json.loads(tasks_json.read_text(encoding="utf-8"))
    tasks: list[dict] = data.get("tasks", [])
    for entry in tasks:
        if entry.get("task_id") == task_id:
            return entry
    raise ValueError(f"Task {task_id} not found in {tasks_json}")


def _load_addendum(plan_path: Path, task_id: str) -> str:
    """Extract the addendum section for task_id from execution_plan.md.

    Returns the text between ``## Addendum: <task_id>`` and the next ``##``
    heading, stripped of leading/trailing whitespace.  Empty string if not found.
    """
    if not plan_path.exists():
        return ""
    text = plan_path.read_text(encoding="utf-8")
    # Match the header line: ## Addendum: T-XXX (anything after the id is ok)
    pattern = rf"^## Addendum: {re.escape(task_id)}(?:\b[^\n]*)?\n(.*?)(?=^##|\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _load_skill(project_root: Path, agent_type: str) -> str:
    """Return the contents of the skill file for agent_type."""
    rel = _SKILL_PATHS.get(agent_type)
    if rel is None:
        raise ValueError(f"Unknown agent_type: {agent_type!r}")
    skill_path = project_root / rel
    return skill_path.read_text(encoding="utf-8")


def assemble_bundle(
    task_id: str,
    agent_type: str,
    project_root: Path,
    out_dir: Path = Path("/tmp"),
    worktree_abs_path: Path | None = None,
) -> Path:
    """Assemble ctx bundle JSON, write to out_dir/ctx-<task_id>-<hash>.json, return path.

    Raises ValueError if task_id is not found in tasks.json.
    Writes atomically via a temp-file + rename; no partial file on error.
    Optionally injects worktree_abs_path into bundle metadata.
    """
    project_root = Path(project_root).resolve()
    out_dir = Path(out_dir).resolve()

    # 1. Resolve task entry (raises ValueError if not found)
    task_entry = _load_task(project_root / "tasks.json", task_id)

    # 2. Parse addendum from execution_plan.md
    addendum = _load_addendum(project_root / "execution_plan.md", task_id)

    # 3. Load skill file
    system_prompt = _load_skill(project_root, agent_type)

    # 4. Assemble payload
    payload: dict = {
        "task_id": task_id,
        "agent_type": agent_type,
        "status": task_entry.get("status", ""),
        "task_description": task_entry.get("description", ""),
        "addendum": addendum,
        "system_prompt": system_prompt,
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        "worktree_abs_path": str(worktree_abs_path.resolve()) if worktree_abs_path else None,
    }

    # 5. Compute 8-char sha256 of the stable content (exclude assembled_at)
    stable = {k: v for k, v in payload.items() if k != "assembled_at"}
    digest = hashlib.sha256(
        json.dumps(stable, sort_keys=True).encode("utf-8")
    ).hexdigest()[:8]

    # 6. Write atomically
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ctx-{task_id}-{digest}.json"
    dest = out_dir / filename

    fd, tmp_path = tempfile.mkstemp(dir=out_dir, prefix=f".tmp-{filename}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_path, dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # 7. Return output path
    return dest

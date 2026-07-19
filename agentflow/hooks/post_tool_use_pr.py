#!/usr/bin/env python3
"""PR fetching, merging, and tracking helper functions for post_tool_use hook."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

def _fetch_merged_pr_titles(limit: int = 20) -> set[str]:
    try:
        r = subprocess.run(["gh", "pr", "list", "--state", "merged", "--json", "title", "--limit", str(limit)],
                           capture_output=True, text=True, timeout=5, check=False)
        return {pr["title"] for pr in json.loads(r.stdout)}
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "fetch_merged_pr_titles_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        return set()


def _is_pr_merge_bash(hook_data: dict) -> bool:
    cmd = hook_data.get("tool_input", {}).get("command", "")
    return "gh pr merge" in cmd or "Merged pull request" in hook_data.get("tool_response", {}).get("output", "")


def _register_pr_url(agentflow_dir: Path, task_id: str, pr_url: str) -> bool:
    """Record PR URL for task_id in .agentflow/task_prs.json (atomic write)."""
    import tempfile
    import os
    prs_file = agentflow_dir / "task_prs.json"
    try:
        data: dict = {}
        if prs_file.exists():
            try:
                data = json.loads(prs_file.read_text())
            except Exception:
                data = {}
        data[task_id] = pr_url
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(agentflow_dir), delete=False, suffix=".tmp", encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, prs_file)
        from agentflow.hooks.post_tool_use_agent import _log
        _log(agentflow_dir, {"event": "task_prs_written", "task_id": task_id, "pr_url": pr_url})
        return True
    except (OSError, ValueError, json.JSONDecodeError) as e:
        from agentflow.hooks.post_tool_use_agent import _log
        _log(agentflow_dir, {"event": "task_prs_write_error", "task_id": task_id, "error": str(e)})
        return False


def _check_pr_state(pr_url: str) -> str | None:
    try:
        r = subprocess.run(["gh", "pr", "view", pr_url, "--json", "state"],
                           capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0:
            return json.loads(r.stdout).get("state")
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use_agent.py", "event": "check_pr_state_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
    return None


def _handle_pr_merge(cmd: str, in_flight: list[str], agentflow_dir: Path, root: Path, tasks_file: Path) -> None:
    """Direct path: extract all PR numbers from gh pr merge N [M...], call gh pr view for each, handle MERGED/OPEN."""
    m = re.search(r'gh pr merge\s+(.*)', cmd)
    if not m:
        return
    pr_nums = re.findall(r'\d+', m.group(1))

    for pr_num in pr_nums:
        try:
            r = subprocess.run(
                ["gh", "pr", "view", pr_num, "--json", "url,title,state"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if r.returncode != 0:
                continue
            data = json.loads(r.stdout)
        except Exception as e:
            print(json.dumps({"hook": "post_tool_use_agent.py", "event": "handle_pr_merge_view_error", "error": str(e), "pr_num": pr_num, "ts": time.time()}), file=sys.stderr)
            continue

        url = data.get("url", "")
        title = data.get("title", "")
        state = data.get("state", "")

        tm = re.search(r'\b(T-\d+)\b', title)
        task_id = tm.group(1) if tm else (in_flight[0] if len(in_flight) == 1 else None)
        if not task_id:
            continue
        from agentflow.hooks.post_tool_use_agent import _log, _mark_task_complete, _run_cleanup
        _log(agentflow_dir, {"event": "pr_merge_direct", "pr_num": pr_num, "task_id": task_id, "state": state})

        if state == "MERGED":
            result = _mark_task_complete(tasks_file, task_id)
            if result in ("marked", "already_complete"):
                _run_cleanup(root)
            try:
                signal_script = root / "agentflow" / "shell" / "pty_signal.py"
                subprocess.run(
                    [sys.executable, str(signal_script), "task_done", task_id],
                    check=False, capture_output=True,
                )
            except Exception as e:
                _log(agentflow_dir, {"event": "handle_pr_merge_signal_error", "error": str(e), "task_id": task_id})
        elif state == "OPEN":
            _register_pr_url(agentflow_dir, task_id, url)

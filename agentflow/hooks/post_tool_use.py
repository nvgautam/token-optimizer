"""PostToolUse hook: reads transcript fill tokens and writes context_fill.json mid-turn.

Fires after every tool call so fill_tokens is current when PTY check_drain_restart
runs on the next IDLE event — eliminates the stale-value race from the Stop hook.

Also detects PR merge events and updates tasks.json + execution_plan.md.
"""
from __future__ import annotations
import contextlib
import fcntl
import json
import os
import pathlib
import re
import sys
import subprocess
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentflow.shell.session_paths import session_file
from agentflow.hooks.fill_utils import compute_fill, extract_fill_from_transcript  # noqa: F401


def _atomic_write(path: pathlib.Path, data_str: str) -> None:
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data_str)
        os.replace(tmp, str(path))
    except Exception as e:
        print(json.dumps({"hook": "post_tool_use.py", "event": "atomic_write_error", "error": str(e), "ts": time.time()}), file=sys.stderr)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _log(agentflow_dir: pathlib.Path, entry: dict) -> None:
    try:
        with open(agentflow_dir / "hook_drain_debug.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), **entry}) + "\n")
    except Exception:
        pass


@contextlib.contextmanager
def _file_lock(lock_path: pathlib.Path):
    """Acquire an exclusive file lock."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def detect_pr_merge(
    tool_name: str,
    tool_input: dict,
    tool_response: dict,
    agentflow_dir: pathlib.Path,
    project_root: pathlib.Path,
) -> None:
    """Detect PR merge event and update tasks.json + execution_plan.md + addendums_archive.md."""
    if tool_name != "Bash":
        return

    output = ""
    if isinstance(tool_response, dict):
        output = tool_response.get("output", "")
    else:
        output = str(tool_response)

    if "✓ Merged pull request" not in output:
        return

    # Note: detect_pr_merge should work for any session type (user CLI, orchestrator, worker, etc).
    # We don't filter by session_type here — we only filter by tool output and task ID presence.

    # Extract task_id from PR title: match conventional commit with task ID
    match = re.search(r'(?:feat|fix|chore|refactor)\((T-\d+)\)', output)
    if not match:
        return

    task_id = match.group(1)

    tasks_path = project_root / "tasks.json"
    ep_path = project_root / "execution_plan.md"
    archive_path = agentflow_dir / "addendums_archive.md"

    lock_tasks = agentflow_dir / "tasks.json.lock"
    lock_ep = agentflow_dir / "execution_plan.md.lock"
    lock_archive = agentflow_dir / "addendums_archive.md.lock"

    def strict_atomic_write(path: pathlib.Path, data_str: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data_str)
            os.replace(tmp, str(path))
        except Exception as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise e

    try:
        with _file_lock(lock_tasks), _file_lock(lock_ep), _file_lock(lock_archive):
            tasks_data = None
            tasks_raw = None
            ep_content = None
            archive_content = None

            if tasks_path.exists():
                tasks_raw = tasks_path.read_text(encoding="utf-8")
                tasks_data = json.loads(tasks_raw)
            if ep_path.exists():
                ep_content = ep_path.read_text(encoding="utf-8")
            if archive_path.exists():
                archive_content = archive_path.read_text(encoding="utf-8")

            if not tasks_data or not ep_content:
                return

            tasks_modified = False
            for task in tasks_data.get("tasks", []):
                if task.get("task_id") == task_id:
                    task["status"] = "complete"
                    tasks_modified = True

            if not tasks_modified:
                return

            ep_lines = ep_content.splitlines(keepends=True)
            new_ep_lines = []
            addendum_content = []
            in_addendum = False

            for line in ep_lines:
                if line.startswith(f"## Addendum: {task_id}"):
                    in_addendum = True
                    addendum_content.append(line)
                    continue

                if in_addendum:
                    if line.startswith("## "):
                        in_addendum = False
                        new_ep_lines.append(line)
                    else:
                        addendum_content.append(line)
                    continue

                if task_id in line and "MERGED" not in line and "|" in line:
                    if not line.rstrip("\n").endswith("MERGED"):
                        line = line.rstrip("\n") + " — MERGED (auto)\n"
                new_ep_lines.append(line)

            new_ep_content = "".join(new_ep_lines)

            new_archive_content = archive_content or ""
            if addendum_content:
                addendum_str = "".join(addendum_content)
                if addendum_str not in new_archive_content:
                    if new_archive_content and not new_archive_content.endswith("\n\n"):
                        new_archive_content += "\n\n"
                    new_archive_content += addendum_str

            try:
                strict_atomic_write(tasks_path, json.dumps(tasks_data, indent=2))
                strict_atomic_write(ep_path, new_ep_content)
                strict_atomic_write(archive_path, new_archive_content)
                _log(agentflow_dir, {"event": "tasks_json_written", "task_id": task_id, "status": "complete"})
            except Exception as e:
                # Rollback - each step independent, preserve original exception
                try:
                    if tasks_raw is not None and tasks_path.exists():
                        strict_atomic_write(tasks_path, tasks_raw)
                except Exception as rb_e:
                    _log(agentflow_dir, {"event": "pr_merge_rollback_error", "step": "tasks", "error": str(rb_e)})
                try:
                    if ep_content is not None and ep_path.exists():
                        strict_atomic_write(ep_path, ep_content)
                except Exception as rb_e:
                    _log(agentflow_dir, {"event": "pr_merge_rollback_error", "step": "ep", "error": str(rb_e)})
                try:
                    if archive_content is not None and archive_path.exists():
                        strict_atomic_write(archive_path, archive_content)
                except Exception as rb_e:
                    _log(agentflow_dir, {"event": "pr_merge_rollback_error", "step": "archive", "error": str(rb_e)})
                raise e
    except Exception as e:
        _log(agentflow_dir, {"event": "pr_merge_hook_error", "task_id": task_id, "error": str(e)})


def _sync_tif_from_disk_if_absent(agentflow_dir: pathlib.Path) -> None:
    """Populate tasks_in_flight.json from current_round.json when tif is absent.

    With the CLI-driven path (`agentflow round start` via Bash), the CLI writes
    both current_round.json and tasks_in_flight.json atomically before this hook
    fires — so this function returns immediately (tif already exists). It remains
    as a safety net for any legacy Write-tool path or race where tif was not written.
    """
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    session_type = "unknown"
    try:
        ss_path = session_file(agentflow_dir, "session_state.json", sid if sid else None)
        if ss_path.exists():
            session_type = json.loads(ss_path.read_text()).get("session_type", "unknown")
    except Exception as e:
        _log(agentflow_dir, {"event": "session_state_read_error", "err": str(e)})

    if session_type != "orchestrator":
        return

    tif_path = session_file(agentflow_dir, "tasks_in_flight.json", sid)
    if tif_path.exists():
        return
    cr_path = agentflow_dir / "current_round.json"
    if not cr_path.exists():
        return
    try:
        task_ids = json.loads(cr_path.read_text()).get("task_ids", [])
        if not isinstance(task_ids, list) or not task_ids:
            return
        _atomic_write(tif_path, json.dumps(task_ids))
        _log(agentflow_dir, {"event": "sync_tif_fallback_written", "task_ids": task_ids})
    except Exception as e:
        _log(agentflow_dir, {"event": "sync_tif_fallback_error", "err": str(e)})


def sync_tasks_in_flight(tool_name: str, tool_input: dict, agentflow_dir: pathlib.Path) -> None:
    """When current_round.json is written, populate tasks_in_flight.json from task_ids.

    Absent tif = round not initialized (PTY skips drain check).
    [] tombstone = drained (PTY may restart).
    Non-empty = tasks running (PTY skips drain check).
    """
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    session_type = "unknown"
    try:
        ss_path = session_file(agentflow_dir, "session_state.json", sid if sid else None)
        if ss_path.exists():
            session_type = json.loads(ss_path.read_text()).get("session_type", "unknown")
    except Exception as e:
        _log(agentflow_dir, {"event": "session_state_read_error", "err": str(e)})

    if session_type != "orchestrator":
        return

    file_path = tool_input.get("file_path", "")
    if tool_name != "Write":
        # CLI-driven path (agentflow round start via Bash): tif already written atomically
        # by the CLI before this hook fires. _sync_tif_from_disk_if_absent is a no-op.
        if file_path.endswith("/.agentflow/current_round.json"):
            _log(agentflow_dir, {"event": "sync_tif_skip", "reason": "not_write_tool", "tool": tool_name})
        _sync_tif_from_disk_if_absent(agentflow_dir)
        return
    if not file_path.endswith("/.agentflow/current_round.json"):
        return
    try:
        task_ids = json.loads(tool_input.get("content", "{}")).get("task_ids", [])
        if not isinstance(task_ids, list) or not task_ids:
            _log(agentflow_dir, {"event": "sync_tif_skip", "reason": "no_task_ids"})
            return
        tif_path = session_file(agentflow_dir, "tasks_in_flight.json", sid)
        _atomic_write(tif_path, json.dumps(task_ids))
        _log(agentflow_dir, {"event": "sync_tif_written", "task_ids": task_ids})
    except Exception as e:
        _log(agentflow_dir, {"event": "sync_tif_error", "err": str(e)})



def audit_orchestrator_direct_write(tool_name: str, tool_input: dict, agentflow_dir: pathlib.Path) -> None:
    """Emit contract_violation if orchestrator writes a non-state file without current_round.json."""
    if tool_name not in ("Write", "Edit"):
        return
    sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
    if not sid:
        return
    try:
        ss = session_file(agentflow_dir, "session_state.json", sid)
        if not ss.exists() or json.loads(ss.read_text()).get("session_type") != "orchestrator":
            return
        fp = tool_input.get("file_path", "")
        if not fp:
            return
        p = pathlib.Path(fp)
        try:
            p.relative_to(agentflow_dir)
            return
        except ValueError:
            pass
        if p.name in {"tasks.json", "execution_plan.md"} or ".claude" in p.parts:
            return
        if not (agentflow_dir / "current_round.json").exists():
            _log(agentflow_dir, {"event": "contract_violation", "rule": "orchestrator_direct_write", "tool": tool_name, "file": fp})
    except Exception:
        pass


def validate_state_files(project_root: Path) -> None:
    # 1. Validate tasks.json
    tasks_path = project_root / "tasks.json"
    if tasks_path.exists():
        try:
            content = tasks_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict) or "tasks" not in data:
                print("Validation Error: tasks.json must be a dict containing a 'tasks' list.", file=sys.stderr)
                sys.exit(1)
            for idx, task in enumerate(data.get("tasks", [])):
                if not isinstance(task, dict):
                    print(f"Validation Error: Task at index {idx} is not a dictionary.", file=sys.stderr)
                    sys.exit(1)
                allowed_keys = {"task_id", "status"}
                actual_keys = set(task.keys())
                missing = allowed_keys - actual_keys
                extra = actual_keys - allowed_keys
                if missing:
                    print(f"Validation Error: Task at index {idx} missing required keys: {missing}", file=sys.stderr)
                    sys.exit(1)
                if extra:
                    print(f"Validation Error: Task at index {idx} contains extra keys not allowed: {extra}", file=sys.stderr)
                    sys.exit(1)
                if task.get("status") not in {"pending", "complete", "cancelled"}:
                    print(f"Validation Error: Task {task.get('task_id')} has invalid status: {task.get('status')}", file=sys.stderr)
                    sys.exit(1)
        except json.JSONDecodeError:
            print("Validation Error: tasks.json is not valid JSON.", file=sys.stderr)
            sys.exit(1)
        except SystemExit:
            raise
        except Exception:
            pass

    # 2. Validate newly added/modified addendums in execution_plan.md
    ep_path = project_root / "execution_plan.md"
    if ep_path.exists():
        try:
            res = subprocess.run(
                ["git", "diff", "-U0", "--", "execution_plan.md"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=False
            )
            new_tids = []
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    # Match line starting with +## Addendum: T-NNN
                    m = re.match(r'^\+## Addendum:\s*(T-\w+)', line)
                    if m:
                        new_tids.append(m.group(1))

            if new_tids:
                content = ep_path.read_text(encoding="utf-8")
                sections = re.split(r'^## Addendum: ', content, flags=re.MULTILINE)
                for sec in sections[1:]:
                    header_line = sec.split('\n')[0]
                    m = re.match(r'(T-\w+)', header_line)
                    if not m:
                        continue
                    tid = m.group(1)
                    if tid in new_tids:
                        if "cancelled" in header_line.lower():
                            continue
                        required_fields = {
                            "**Goal:**": "Goal",
                            "**Files:**": "Files",
                            "**Test scenarios:**": "Test scenarios",
                            "**OWNS:**": "OWNS",
                            "**estimated_lines:**": "estimated_lines"
                        }
                        for field, label in required_fields.items():
                            if field not in sec:
                                print(f"Validation Error: Addendum for {tid} is missing required field: {field}", file=sys.stderr)
                                sys.exit(1)
        except SystemExit:
            raise
        except Exception:
            pass


def main() -> None:
    project_root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    agentflow_dir = project_root / ".agentflow"
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        payload = json.loads(sys.stdin.read())
        validate_state_files(project_root)
        tn, ti = payload.get("tool_name", ""), payload.get("tool_input", {})
        sync_tasks_in_flight(tn, ti, agentflow_dir)
        audit_orchestrator_direct_write(tn, ti, agentflow_dir)
        detect_pr_merge(tn, ti, payload.get("tool_response", {}), agentflow_dir, project_root)

        transcript_path = payload.get("transcript_path", "")
        fill_tokens = extract_fill_from_transcript(transcript_path)
        if fill_tokens is None:
            sys.exit(0)

        sid = os.environ.get("AGENTFLOW_SESSION_ID", "")
        fill_path = session_file(agentflow_dir, "context_fill.json", sid if sid else None)
        _atomic_write(fill_path, json.dumps({"fill_tokens": fill_tokens, "ts": time.time()}))
        _log(agentflow_dir, {"event": "context_fill_written", "fill_tokens": fill_tokens, "sid": sid})
    except Exception as e:
        _log(agentflow_dir, {"event": "context_fill_write_error", "error": str(e)})
    sys.exit(0)


if __name__ == "__main__":
    main()

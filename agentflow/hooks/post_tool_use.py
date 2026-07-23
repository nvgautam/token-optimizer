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
from agentflow.config import constants


def _atomic_write(path: pathlib.Path, data_str: str) -> None:
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        with os.fdopen(fd, "w", encoding=constants.UTF8) as f:
            f.write(data_str)
        os.replace(tmp, str(path))
    except Exception as e:
        print(json.dumps({constants.HOOK_FIELD_HOOK: constants.HOOK_POST_TOOL_USE, constants.HOOK_FIELD_EVENT: "atomic_write_error", constants.HOOK_FIELD_ERROR: str(e), constants.HOOK_FIELD_TS: time.time()}), file=sys.stderr)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _log(agentflow_dir: pathlib.Path, entry: dict) -> None:
    from agentflow.shell.audit_logger import flush_writes, write_audit
    event = entry.get("event", "unknown")
    source = entry.get("source", "hook")
    level = entry.get("level", "INFO")
    session_type = entry.get("session_type")
    extra = {k: v for k, v in entry.items() if k not in {"event", "source", "level", "session_type"}}
    write_audit(agentflow_dir / constants.FILE_HOOK_DRAIN_DEBUG, event=event, source=source, level=level, session_type=session_type, **extra)
    flush_writes()


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
    if tool_name != constants.TOOL_BASH:
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

    tasks_path = project_root / constants.FILE_TASKS_JSON
    ep_path = project_root / constants.FILE_EXECUTION_PLAN
    archive_path = agentflow_dir / constants.FILE_ADDENDUMS_ARCHIVE

    lock_tasks = agentflow_dir / constants.LOCK_TASKS_JSON
    lock_ep = agentflow_dir / constants.LOCK_EXECUTION_PLAN
    lock_archive = agentflow_dir / constants.LOCK_ADDENDUMS_ARCHIVE

    def strict_atomic_write(path: pathlib.Path, data_str: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding=constants.UTF8) as f:
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
                tasks_raw = tasks_path.read_text(encoding=constants.UTF8)
                tasks_data = json.loads(tasks_raw)
            if ep_path.exists():
                ep_content = ep_path.read_text(encoding=constants.UTF8)
            if archive_path.exists():
                archive_content = archive_path.read_text(encoding=constants.UTF8)

            if not tasks_data or not ep_content:
                return

            tasks_modified = False
            for task in tasks_data.get(constants.KEY_TASKS, []):
                if task.get(constants.KEY_TASK_ID) == task_id:
                    task[constants.KEY_STATUS] = constants.STATUS_COMPLETE
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
                _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "tasks_json_written", constants.KEY_TASK_ID: task_id, constants.KEY_STATUS: constants.STATUS_COMPLETE})
            except Exception as e:
                # Rollback - each step independent, preserve original exception
                try:
                    if tasks_raw is not None and tasks_path.exists():
                        strict_atomic_write(tasks_path, tasks_raw)
                except Exception as rb_e:
                    _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "pr_merge_rollback_error", "step": "tasks", constants.HOOK_FIELD_ERROR: str(rb_e)})
                try:
                    if ep_content is not None and ep_path.exists():
                        strict_atomic_write(ep_path, ep_content)
                except Exception as rb_e:
                    _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "pr_merge_rollback_error", "step": "ep", constants.HOOK_FIELD_ERROR: str(rb_e)})
                try:
                    if archive_content is not None and archive_path.exists():
                        strict_atomic_write(archive_path, archive_content)
                except Exception as rb_e:
                    _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "pr_merge_rollback_error", "step": "archive", constants.HOOK_FIELD_ERROR: str(rb_e)})
                raise e
    except Exception as e:
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "pr_merge_hook_error", constants.KEY_TASK_ID: task_id, constants.HOOK_FIELD_ERROR: str(e)})


def _sync_tif_from_disk_if_absent(agentflow_dir: pathlib.Path) -> None:
    """Populate tasks_in_flight.json from current_round.json when tif is absent.

    With the CLI-driven path (`agentflow round start` via Bash), the CLI writes
    both current_round.json and tasks_in_flight.json atomically before this hook
    fires — so this function returns immediately (tif already exists). It remains
    as a safety net for any legacy Write-tool path or race where tif was not written.
    """
    sid = os.environ.get(constants.ENV_SESSION_ID, "")
    session_type = constants.SESSION_TYPE_UNKNOWN
    try:
        ss_path = session_file(agentflow_dir, constants.FILE_SESSION_STATE, sid if sid else None)
        if ss_path.exists():
            session_type = json.loads(ss_path.read_text()).get(constants.KEY_SESSION_TYPE, constants.SESSION_TYPE_UNKNOWN)
    except Exception as e:
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "session_state_read_error", "err": str(e)})

    if session_type != constants.SESSION_TYPE_ORCHESTRATOR:
        return

    tif_path = session_file(agentflow_dir, constants.FILE_TASKS_IN_FLIGHT, sid)
    if tif_path.exists():
        return
    cr_path = agentflow_dir / constants.FILE_CURRENT_ROUND
    if not cr_path.exists():
        return
    try:
        task_ids = json.loads(cr_path.read_text()).get(constants.KEY_TASK_IDS, [])
        if not isinstance(task_ids, list) or not task_ids:
            return
        _atomic_write(tif_path, json.dumps(task_ids))
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "sync_tif_fallback_written", constants.KEY_TASK_IDS: task_ids})
    except Exception as e:
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "sync_tif_fallback_error", "err": str(e)})


def sync_tasks_in_flight(tool_name: str, tool_input: dict, agentflow_dir: pathlib.Path) -> None:
    """When current_round.json is written, populate tasks_in_flight.json from task_ids.

    Absent tif = round not initialized (PTY skips drain check).
    [] tombstone = drained (PTY may restart).
    Non-empty = tasks running (PTY skips drain check).
    """
    sid = os.environ.get(constants.ENV_SESSION_ID, "")
    session_type = constants.SESSION_TYPE_UNKNOWN
    try:
        ss_path = session_file(agentflow_dir, constants.FILE_SESSION_STATE, sid if sid else None)
        if ss_path.exists():
            session_type = json.loads(ss_path.read_text()).get(constants.KEY_SESSION_TYPE, constants.SESSION_TYPE_UNKNOWN)
    except Exception as e:
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "session_state_read_error", "err": str(e)})

    if session_type != constants.SESSION_TYPE_ORCHESTRATOR:
        return

    file_path = tool_input.get(constants.KEY_FILE_PATH, "")
    if tool_name != constants.TOOL_WRITE:
        # CLI-driven path (agentflow round start via Bash): tif already written atomically
        # by the CLI before this hook fires. _sync_tif_from_disk_if_absent is a no-op.
        if file_path.endswith(f"/{constants.DIR_AGENTFLOW}/{constants.FILE_CURRENT_ROUND}"):
            _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "sync_tif_skip", "reason": "not_write_tool", "tool": tool_name})
        _sync_tif_from_disk_if_absent(agentflow_dir)
        return
    if not file_path.endswith(f"/{constants.DIR_AGENTFLOW}/{constants.FILE_CURRENT_ROUND}"):
        return
    try:
        task_ids = json.loads(tool_input.get(constants.KEY_CONTENT, "{}")).get(constants.KEY_TASK_IDS, [])
        if not isinstance(task_ids, list) or not task_ids:
            _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "sync_tif_skip", "reason": "no_task_ids"})
            return
        tif_path = session_file(agentflow_dir, constants.FILE_TASKS_IN_FLIGHT, sid)
        _atomic_write(tif_path, json.dumps(task_ids))
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "sync_tif_written", constants.KEY_TASK_IDS: task_ids})
    except Exception as e:
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "sync_tif_error", "err": str(e)})



def audit_orchestrator_direct_write(tool_name: str, tool_input: dict, agentflow_dir: pathlib.Path) -> None:
    """Emit contract_violation if orchestrator writes a non-state file without current_round.json."""
    if tool_name not in (constants.TOOL_WRITE, constants.TOOL_EDIT):
        return
    sid = os.environ.get(constants.ENV_SESSION_ID, "")
    if not sid:
        return
    try:
        ss = session_file(agentflow_dir, constants.FILE_SESSION_STATE, sid)
        if not ss.exists() or json.loads(ss.read_text()).get(constants.KEY_SESSION_TYPE) != constants.SESSION_TYPE_ORCHESTRATOR:
            return
        fp = tool_input.get(constants.KEY_FILE_PATH, "")
        if not fp:
            return
        p = pathlib.Path(fp)
        try:
            p.relative_to(agentflow_dir)
            return
        except ValueError:
            pass
        if p.name in {constants.FILE_TASKS_JSON, constants.FILE_EXECUTION_PLAN} or ".claude" in p.parts:
            return
        if not (agentflow_dir / constants.FILE_CURRENT_ROUND).exists():
            _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "contract_violation", "rule": "orchestrator_direct_write", "tool": tool_name, "file": fp})
    except Exception:
        pass


def validate_state_files(project_root: Path) -> None:
    # 1. Validate tasks.json
    tasks_path = project_root / constants.FILE_TASKS_JSON
    if tasks_path.exists():
        try:
            content = tasks_path.read_text(encoding=constants.UTF8)
            data = json.loads(content)
            if not isinstance(data, dict) or constants.KEY_TASKS not in data:
                print("Validation Error: tasks.json must be a dict containing a 'tasks' list.", file=sys.stderr)
                sys.exit(1)
            for idx, task in enumerate(data.get(constants.KEY_TASKS, [])):
                if not isinstance(task, dict):
                    print(f"Validation Error: Task at index {idx} is not a dictionary.", file=sys.stderr)
                    sys.exit(1)
                allowed_keys = {constants.KEY_TASK_ID, constants.KEY_STATUS}
                actual_keys = set(task.keys())
                missing = allowed_keys - actual_keys
                extra = actual_keys - allowed_keys
                if missing:
                    print(f"Validation Error: Task at index {idx} missing required keys: {missing}", file=sys.stderr)
                    sys.exit(1)
                if extra:
                    print(f"Validation Error: Task at index {idx} contains extra keys not allowed: {extra}", file=sys.stderr)
                    sys.exit(1)
                if task.get(constants.KEY_STATUS) not in {constants.STATUS_PENDING, constants.STATUS_COMPLETE, constants.STATUS_CANCELLED}:
                    print(f"Validation Error: Task {task.get(constants.KEY_TASK_ID)} has invalid status: {task.get(constants.KEY_STATUS)}", file=sys.stderr)
                    sys.exit(1)
        except json.JSONDecodeError:
            print("Validation Error: tasks.json is not valid JSON.", file=sys.stderr)
            sys.exit(1)
        except SystemExit:
            raise
        except Exception:
            pass

    # 2. Validate newly added/modified addendums in execution_plan.md
    ep_path = project_root / constants.FILE_EXECUTION_PLAN
    if ep_path.exists():
        try:
            res = subprocess.run(
                ["git", "diff", "-U0", "--", constants.FILE_EXECUTION_PLAN],
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
                content = ep_path.read_text(encoding=constants.UTF8)
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
    project_root = pathlib.Path(os.environ.get(constants.ENV_CLAUDE_PROJECT_DIR, os.getcwd()))
    agentflow_dir = project_root / constants.DIR_AGENTFLOW
    try:
        agentflow_dir.mkdir(parents=True, exist_ok=True)
        payload = json.loads(sys.stdin.read())
        validate_state_files(project_root)
        tn, ti = payload.get(constants.KEY_TOOL_NAME, ""), payload.get(constants.KEY_TOOL_INPUT, {})
        sync_tasks_in_flight(tn, ti, agentflow_dir)
        audit_orchestrator_direct_write(tn, ti, agentflow_dir)
        detect_pr_merge(tn, ti, payload.get(constants.KEY_TOOL_RESPONSE, {}), agentflow_dir, project_root)

        transcript_path = payload.get(constants.KEY_TRANSCRIPT_PATH, "")
        fill_tokens = extract_fill_from_transcript(transcript_path)
        if fill_tokens is None:
            sys.exit(0)

        sid = os.environ.get(constants.ENV_SESSION_ID, "")
        fill_path = session_file(agentflow_dir, constants.FILE_CONTEXT_FILL, sid if sid else None)
        _atomic_write(fill_path, json.dumps({constants.KEY_FILL_TOKENS: fill_tokens, constants.KEY_TS: time.time()}))
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "context_fill_written", constants.KEY_FILL_TOKENS: fill_tokens, constants.KEY_SID: sid})
        if sid:
            try:
                active_file = session_file(agentflow_dir, "agent_active.json", sid)
                if active_file.exists():
                    active_file.write_text(json.dumps({"active": True, "ts": time.time()}), encoding="utf-8")
            except Exception:
                pass
    except Exception as e:
        _log(agentflow_dir, {constants.HOOK_FIELD_EVENT: "context_fill_write_error", constants.HOOK_FIELD_ERROR: str(e)})
    sys.exit(0)


if __name__ == "__main__":
    main()

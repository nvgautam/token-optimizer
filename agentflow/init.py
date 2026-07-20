"""AgentFlow first-run init: interactive or silent setup on first PTY start."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

_STATE_FILE = Path.home() / ".agentflow" / "config.json"
_GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
_BUNDLE_PATH = Path.home() / ".agentflow" / "skills" / "bundle-v1.enc"

_GIT_PERMS = ["Bash(git push *)", "Bash(gh pr create *)", "Bash(gh pr merge *)"]


def _h(name: str, env: str = "") -> dict:
    prefix = f"{env} " if env else ""
    return {"type": "command", "command": f'{prefix}python3 "$CLAUDE_PROJECT_DIR/agentflow/hooks/{name}"'}


_AGENTFLOW_HOOKS: dict = {
    "UserPromptSubmit": [
        {"hooks": [_h("idx_reminder.py"), _h("verbosity_reminder.py"), _h("user_prompt_submit.py")]},
    ],
    "PreToolUse": [
        {"matcher": "Read", "hooks": [_h("read_logger.py"), _h("read_check.py")]},
        {"matcher": "Agent", "hooks": [_h("pre_tool_use_agent.py")]},
        {"matcher": ".*", "hooks": [_h("payload_inspector.py", "AGENTFLOW_HOOK_EVENT=PreToolUse")]},
    ],
    "Stop": [
        {"hooks": [_h("payload_inspector.py", "AGENTFLOW_HOOK_EVENT=Stop"), _h("stop_context_capture.py")]},
    ],
    "PostToolUse": [
        {"hooks": [_h("post_tool_use.py")]},
        {"matcher": "Write", "hooks": [_h("write_indexer.py"), _h("size_check.py")]},
        {"matcher": "Edit", "hooks": [_h("write_indexer.py"), _h("size_check.py")]},
        {"matcher": "Agent", "hooks": [_h("post_tool_use_agent.py")]},
        {"matcher": "Bash", "hooks": [_h("post_tool_use_agent.py")]},
    ],
}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON atomically via temp-file rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _extract_commands(entries: list) -> set:
    """Collect all hook command strings from a list of hook-entry dicts."""
    cmds: set = set()
    for entry in entries:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if cmd:
                cmds.add(cmd)
    return cmds


def _is_initialized(project_root: Path) -> bool:
    try:
        return bool(_read_json(_STATE_FILE).get("initialized", False))
    except Exception:
        return False


def _mark_initialized(project_root: Path) -> None:
    data = _read_json(_STATE_FILE)
    data["initialized"] = True
    _write_json_atomic(_STATE_FILE, data)


def _register_headroom_mcp() -> None:
    """Add headroom to allowedMcpServers in global ~/.claude/settings.json."""
    data = _read_json(_GLOBAL_SETTINGS)
    servers: list = data.setdefault("allowedMcpServers", [])
    if not any(s.get("serverName") == "headroom" for s in servers):
        servers.append({"serverName": "headroom"})
        _write_json_atomic(_GLOBAL_SETTINGS, data)


def _deep_merge_project_settings(project_root: Path) -> None:
    """Merge agentflow hooks into project .claude/settings.json (non-destructive).

    Also moves Stop hook and autoCompactEnabled from global to project level.
    """
    proj_path = project_root / ".claude" / "settings.json"
    data = _read_json(proj_path)
    hooks = data.setdefault("hooks", {})

    # Add agentflow hook entries not already present (keyed by command string)
    for event, entries in _AGENTFLOW_HOOKS.items():
        existing_cmds = _extract_commands(hooks.get(event, []))
        for entry in entries:
            entry_cmds = _extract_commands([entry])
            if entry_cmds and not entry_cmds.issubset(existing_cmds):
                hooks.setdefault(event, []).append(entry)
                existing_cmds |= entry_cmds

    # Read global settings once — remove Stop hook and autoCompactEnabled
    global_data = _read_json(_GLOBAL_SETTINGS)
    global_changed = False

    global_hooks = global_data.get("hooks", {})
    if "Stop" in global_hooks:
        stop_entries = global_hooks.pop("Stop")
        if not global_hooks:
            global_data.pop("hooks", None)
        else:
            global_data["hooks"] = global_hooks
        # Absorb stop entries into project if not already present
        existing_stop = _extract_commands(hooks.get("Stop", []))
        for entry in stop_entries:
            entry_cmds = _extract_commands([entry])
            if entry_cmds and not entry_cmds.issubset(existing_stop):
                hooks.setdefault("Stop", []).append(entry)
                existing_stop |= entry_cmds
        global_changed = True

    if "autoCompactEnabled" in global_data:
        data.setdefault("autoCompactEnabled", global_data.pop("autoCompactEnabled"))
        global_changed = True
    else:
        data.setdefault("autoCompactEnabled", False)

    if global_changed:
        _write_json_atomic(_GLOBAL_SETTINGS, global_data)
    _write_json_atomic(proj_path, data)


def _add_git_permissions(project_root: Path) -> None:
    """Add git/gh permission entries to project settings (idempotent)."""
    proj_path = project_root / ".claude" / "settings.json"
    data = _read_json(proj_path)
    perms: list = data.setdefault("permissions", {}).setdefault("allow", [])
    for perm in _GIT_PERMS:
        if perm not in perms:
            perms.append(perm)
    _write_json_atomic(proj_path, data)


def _download_skill_bundle() -> None:
    """Download encrypted skill bundle if AGENTFLOW_ENCRYPT=true and not present."""
    if os.environ.get("AGENTFLOW_ENCRYPT", "false").lower() != "true":
        return
    if _BUNDLE_PATH.exists():
        return
    url = os.environ.get("AGENTFLOW_BUNDLE_URL", "")
    if not url:
        sys.stderr.write(
            "[agentflow] AGENTFLOW_BUNDLE_URL not set — skill bundle not downloaded.\n"
        )
        return
    _BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url) as resp:
            bundle_data = resp.read()
        fd, tmp = tempfile.mkstemp(dir=_BUNDLE_PATH.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(bundle_data)
            os.replace(tmp, _BUNDLE_PATH)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except urllib.error.URLError as exc:
        sys.stderr.write(f"[agentflow] skill bundle download failed: {exc}\n")


def _run_interactive(project_root: Path) -> None:
    """Interactive first-run setup — asks 2 plain-English questions."""
    print("[agentflow] First-run setup (press Enter to accept defaults):", flush=True)

    mcp_ans = input("  Allow MCP auto-install? [y/N] ").strip().lower()
    allow_mcp = mcp_ans in ("y", "yes")

    git_ans = input("  Allow git operations (git push, gh pr create/merge)? [Y/n] ").strip().lower()
    allow_git = git_ans not in ("n", "no")

    _deep_merge_project_settings(project_root)
    _register_headroom_mcp()

    global_data = _read_json(_GLOBAL_SETTINGS)
    global_data["allowManagedMcpServersOnly"] = allow_mcp
    _write_json_atomic(_GLOBAL_SETTINGS, global_data)

    if allow_git:
        _add_git_permissions(project_root)

    _download_skill_bundle()
    _mark_initialized(project_root)
    print("[agentflow] Setup complete.", flush=True)


def _run_silent(project_root: Path) -> None:
    """Non-TTY path: write safe defaults silently, print one-line guidance."""
    sys.stderr.write(
        "[agentflow] Non-TTY context detected — writing safe defaults. "
        "Run 'agentflow init' in a terminal to customize.\n"
    )
    _deep_merge_project_settings(project_root)
    _register_headroom_mcp()
    _add_git_permissions(project_root)
    _mark_initialized(project_root)


def check_and_run(project_root: Path) -> None:
    """Entry point: detect first run and execute init if needed."""
    if _is_initialized(project_root):
        return
    if sys.stdin.isatty():
        _run_interactive(project_root)
    else:
        _run_silent(project_root)

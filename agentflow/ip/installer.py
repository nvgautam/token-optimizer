"""Install / uninstall agentflow hooks into customer ~/.claude/settings.json."""

import json
import os
import re
from pathlib import Path
from typing import Any

# Pattern: python3 "$CLAUDE_PROJECT_DIR/agentflow/hooks/<name>.py"
_PROJECT_HOOK_RE = re.compile(
    r"""python3\s+"?\$CLAUDE_PROJECT_DIR/agentflow/hooks/(\w+)\.py"?"""
)

_AF_TAG = "agentflow hooks"


def _transform_command(cmd: str) -> str:
    """Convert a project-relative hook command to a binary-relative one.

    python3 "$CLAUDE_PROJECT_DIR/agentflow/hooks/read_check.py"
    → agentflow hooks read_check

    Commands already in binary form are returned unchanged.
    """
    m = _PROJECT_HOOK_RE.search(cmd)
    if m:
        return f"{_AF_TAG} {m.group(1)}"
    return cmd


def _load_settings(path: Path) -> dict[str, Any]:
    """Load JSON from *path*; return empty dict if missing or malformed."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as JSON to *path* atomically via a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, str(path))


def _find_block(blocks: list[dict], matcher: str | None) -> dict | None:
    """Return the first block whose matcher matches (or both are absent)."""
    for block in blocks:
        if block.get("matcher") == matcher:
            return block
    return None


def _merge_hooks(
    destination: dict[str, Any],
    agentflow_hooks: dict[str, list[dict]],
) -> dict[str, Any]:
    """Deep-merge *agentflow_hooks* into *destination* hooks section.

    Idempotent: duplicate commands (by command string) are never added.
    """
    dest_hooks: dict[str, list] = destination.setdefault("hooks", {})

    for event_type, af_blocks in agentflow_hooks.items():
        if event_type not in dest_hooks:
            dest_hooks[event_type] = []

        dest_blocks: list = dest_hooks[event_type]

        for af_block in af_blocks:
            matcher = af_block.get("matcher")  # may be None
            af_cmds = [h["command"] for h in af_block.get("hooks", [])]

            existing_block = _find_block(dest_blocks, matcher)

            if existing_block is None:
                # No matching block — append a fresh one (only new commands)
                new_hooks = [
                    {"type": "command", "command": cmd}
                    for cmd in af_cmds
                ]
                if new_hooks:
                    new_block: dict[str, Any] = {"hooks": new_hooks}
                    if matcher is not None:
                        new_block["matcher"] = matcher
                    dest_blocks.append(new_block)
            else:
                # Matching block found — add missing commands only
                present = {h["command"] for h in existing_block.get("hooks", [])}
                for cmd in af_cmds:
                    if cmd not in present:
                        existing_block.setdefault("hooks", []).append(
                            {"type": "command", "command": cmd}
                        )
                        present.add(cmd)

    return destination


def _read_project_hooks(project_root: Path) -> dict[str, list[dict]]:
    """Read hooks from <project_root>/.claude/settings.json and transform commands."""
    settings_path = project_root / ".claude" / "settings.json"
    data = _load_settings(settings_path)
    raw_hooks: dict[str, list] = data.get("hooks", {})

    transformed: dict[str, list[dict]] = {}
    for event_type, blocks in raw_hooks.items():
        new_blocks = []
        for block in blocks:
            new_block = {k: v for k, v in block.items() if k != "hooks"}
            new_block["hooks"] = [
                {"type": h.get("type", "command"), "command": _transform_command(h["command"])}
                for h in block.get("hooks", [])
                if "command" in h
            ]
            new_blocks.append(new_block)
        transformed[event_type] = new_blocks
    return transformed


def install(project_root: Path | None = None) -> None:
    """Install agentflow hooks from the project's .claude/settings.json into
    ~/.claude/settings.json.  Idempotent and non-destructive.
    """
    if project_root is None:
        project_root = Path.cwd()

    af_hooks = _read_project_hooks(project_root)

    home_settings = Path.home() / ".claude" / "settings.json"
    destination = _load_settings(home_settings)

    _merge_hooks(destination, af_hooks)

    _write_atomic(home_settings, destination)
    print(f"agentflow: hooks installed → {home_settings}")


def uninstall() -> None:
    """Remove agentflow hook entries from ~/.claude/settings.json.

    Only removes entries whose command contains 'agentflow hooks'.
    All other hooks and settings are preserved.
    """
    home_settings = Path.home() / ".claude" / "settings.json"
    if not home_settings.exists():
        return

    data = _load_settings(home_settings)
    hooks = data.get("hooks", {})

    for event_type in list(hooks.keys()):
        blocks = hooks[event_type]
        new_blocks = []
        for block in blocks:
            remaining = [
                h for h in block.get("hooks", [])
                if _AF_TAG not in h.get("command", "")
            ]
            if remaining:
                block = {**block, "hooks": remaining}
                new_blocks.append(block)
            # drop block entirely if no hooks remain after removal
        hooks[event_type] = new_blocks
        if not new_blocks:
            del hooks[event_type]

    _write_atomic(home_settings, data)
    print(f"agentflow: hooks uninstalled from {home_settings}")

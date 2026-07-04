#!/usr/bin/env python3
"""UserPromptSubmit hook: inject verbosity reminder every 2 turns (invisible to user input field)."""

import os
import sys
from pathlib import Path

INTERVAL = 2
COUNTER_FILE = Path.home() / ".agentflow" / "verbosity_turn_counter"

# T-081: lets an A/B comparison disable the hook entirely for one arm
# (agentflow/shadow/verbosity_ab.py) without touching session_manager.py.
_DISABLED_VALUES = {"1", "true", "yes", "on"}


def _hook_disabled() -> bool:
    return os.environ.get("AGENTFLOW_VERBOSITY_HOOK_DISABLED", "").strip().lower() in _DISABLED_VALUES


def _arm_suppressed() -> bool:
    """Return True if the A/B arm file says 'off' (suppress reminder)."""
    project_root = os.environ.get("AGENTFLOW_PROJECT_ROOT", "")
    candidates = []
    if project_root:
        candidates.append(Path(project_root) / ".agentflow" / "verbosity_ab_arm.txt")
    candidates.append(Path.home() / ".agentflow" / "verbosity_ab_arm.txt")
    for path in candidates:
        if path.exists():
            return path.read_text().strip() == "off"
    return False


def main() -> None:
    if _hook_disabled():
        sys.exit(0)
    if _arm_suppressed():
        sys.exit(0)

    try:
        count = int(COUNTER_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        count = 0

    count += 1
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(str(count))

    if count % INTERVAL == 0:
        # Wrapped in a non-HTML tag so headroom's tag_protector (T-080)
        # keeps it verbatim — a hook's stdout isn't a tool_result block,
        # so exclude_tools config can't protect it any other way.
        print("<agentflow-reminder>[VERBOSITY] Keep responses concise (≤ 3 sentences / ~150 tokens).</agentflow-reminder>")

    sys.exit(0)


if __name__ == "__main__":
    main()

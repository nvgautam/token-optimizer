#!/usr/bin/env python3
"""UserPromptSubmit hook: inject verbosity reminder every 2 turns (invisible to user input field)."""

import sys
from pathlib import Path

INTERVAL = 2
COUNTER_FILE = Path.home() / ".agentflow" / "verbosity_turn_counter"


def main() -> None:
    try:
        count = int(COUNTER_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        count = 0

    count += 1
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(str(count))

    if count % INTERVAL == 0:
        print("[VERBOSITY] Keep responses concise (≤ 3 sentences / ~150 tokens).")

    sys.exit(0)


if __name__ == "__main__":
    main()

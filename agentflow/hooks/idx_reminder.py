#!/usr/bin/env python3
"""UserPromptSubmit hook: inject .idx reminder every 3 turns (invisible to user input field)."""

import hashlib
import os
import sys
from pathlib import Path

INTERVAL = 3
COUNTER_FILE = Path.home() / ".agentflow" / "idx_turn_counter"


def main() -> None:
    try:
        count = int(COUNTER_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        count = 0

    count += 1
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(str(count))

    if count % INTERVAL == 0:
        cwd_hash = hashlib.sha256(os.getcwd().encode()).hexdigest()
        print(
            f"[IDX] Before any Read: check"
            f" ~/.agentflow/cache/{cwd_hash}/index/<file>.idx first"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()

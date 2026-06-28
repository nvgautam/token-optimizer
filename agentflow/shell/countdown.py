"""PTY pre-restart countdown timer.

Stdlib-only. Zero LLM calls. Fully deterministic.
"""
from __future__ import annotations

import sys
import time


def countdown(seconds: int, on_complete, message: str = "") -> None:
    """Print per-second countdown to stderr; call on_complete when done.

    KeyboardInterrupt exits cleanly — no traceback, on_complete not called.
    """
    try:
        for remaining in range(seconds, 0, -1):
            sys.stderr.write(f"\rRestarting in {remaining}s...")
            sys.stderr.flush()
            time.sleep(1)
        sys.stderr.write("\r" + " " * 30 + "\r")
        sys.stderr.flush()
        on_complete()
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        sys.stderr.flush()

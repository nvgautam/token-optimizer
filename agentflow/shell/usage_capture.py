"""Usage capture: inject /usage into Claude Code PTY and write stats to ledger.

Functions
---------
parse_usage_output  — regex-extract window stats from /usage text
write_usage_to_ledger — atomic append to agentflow_ledger.json
capture_usage       — inject /usage into wrapper, read output, parse
"""
from __future__ import annotations

import datetime
import json
import os
import re
import select
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Regex patterns for Claude Code /usage output
# ---------------------------------------------------------------------------

# Matches:  5-hour window: 18% (56,231 / 310,230 tokens) — resets in 3h 42m
_5HR_RE = re.compile(
    r"5.hour\s+window[:\s]*(\d+)%\s*\("
    r"[\d,]+\s*/\s*([\d,]+)\s*tokens?\)"
    r".*?resets\s+in\s+(?:(\d+)h\s*)?(?:(\d+)m)?",
    re.IGNORECASE | re.DOTALL,
)

# Matches:  Weekly window: 5% (15,512 / 310,230 tokens) — resets Jul 14
#       or: Weekly window: 5% (15,512 / 310,230 tokens) — resets in 1h 30m
_WKLY_RE = re.compile(
    r"[Ww]eekly\s+window[:\s]*(\d+)%\s*\("
    r"[\d,]+\s*/\s*([\d,]+)\s*tokens?\)"
    r"(?:.*?resets\s+in\s+(?:(\d+)h\s*)?(?:(\d+)m)?)?",
    re.IGNORECASE | re.DOTALL,
)


def _parse_int(s: Optional[str]) -> int:
    """Strip commas and convert to int; return 0 for None/empty."""
    return int(s.replace(",", "")) if s else 0


def parse_usage_output(text: str) -> Optional[dict]:
    """Parse Claude Code /usage output; return dict or None on failure."""
    m5 = _5HR_RE.search(text)
    mw = _WKLY_RE.search(text)
    if not m5 or not mw:
        return None

    pct_5hr = int(m5.group(1))
    cap_5hr = _parse_int(m5.group(2))
    reset_5h = int(m5.group(3)) if m5.group(3) else 0
    reset_5m = int(m5.group(4)) if m5.group(4) else 0
    reset_min_5hr = reset_5h * 60 + reset_5m

    pct_wkly = int(mw.group(1))
    cap_wkly = _parse_int(mw.group(2))
    # weekly reset may be a date ("resets Jul 14"); only extract if time present
    if mw.group(3) or mw.group(4):
        reset_min_wkly: Optional[int] = (
            int(mw.group(3) or 0) * 60 + int(mw.group(4) or 0)
        )
    else:
        reset_min_wkly = None

    return {
        "start_pct_5hr": pct_5hr,
        "start_pct_wkly": pct_wkly,
        "cap_5hr": cap_5hr,
        "cap_wkly": cap_wkly,
        "reset_min_5hr": reset_min_5hr,
        "reset_min_wkly": reset_min_wkly,
    }


def write_usage_to_ledger(usage: dict, ledger_path: Path, label: str) -> None:
    """Atomically append a usage snapshot to ledger_path's usage_snapshots list."""
    try:
        if ledger_path.exists():
            data: dict = json.loads(ledger_path.read_text(encoding="utf-8"))
        else:
            data = {}

        snapshots: list = data.setdefault("usage_snapshots", [])
        entry = {"label": label, "ts": datetime.datetime.now().isoformat()}
        entry.update(usage)
        snapshots.append(entry)

        tmp = ledger_path.with_suffix(".usage_tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(ledger_path)
    except Exception:  # noqa: BLE001 — non-fatal, never crash the shell
        pass


def capture_usage(wrapper, timeout: float = 3.0, passthrough_fd: Optional[int] = None) -> Optional[dict]:
    """Inject /usage into the PTY wrapper and parse the response.

    Parameters
    ----------
    wrapper:
        PTYWrapper instance with ``write_input(str)`` and ``master_fd`` (int).
    timeout:
        Total seconds to wait for output.
    passthrough_fd:
        If set, bytes read from master_fd are also written to this fd (e.g. 1
        for stdout). Required at session start so the claude startup render is
        not swallowed before the main loop begins.

    Returns
    -------
    Parsed usage dict, or None if injection/parsing fails.
    """
    try:
        wrapper.write_input("/usage\r")
        deadline = time.monotonic() + timeout
        chunks: list[bytes] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([wrapper.master_fd], [], [], min(0.1, remaining))
            if not ready:
                continue
            try:
                chunk = os.read(wrapper.master_fd, 4096)
                if chunk:
                    chunks.append(chunk)
                    if passthrough_fd is not None:
                        os.write(passthrough_fd, chunk)
            except OSError:
                break

        text = b"".join(chunks).decode("utf-8", errors="replace")
        return parse_usage_output(text)
    except Exception:  # noqa: BLE001 — non-fatal
        return None

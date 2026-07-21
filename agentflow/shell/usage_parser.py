"""Provider usage limit parser for Claude and Gemini /usage output.

Functions
---------
parse_claude_usage       — parse Claude /usage (session + weekly % + resets_at)
parse_gemini_usage       — parse Gemini /usage (weekly + 5hr % + refreshes_in)
capture_provider_usage   — inject /usage into PTY, capture output, dispatch parser
"""
from __future__ import annotations

import os
import re
import select
import time
from typing import Optional

# ---------------------------------------------------------------------------
# ANSI stripping
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|[()][AB]|\][\d;]*(?:\x07|\x1b\\))")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences, leaving Unicode block chars intact."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Claude /usage parser
#
# Expected output (after ANSI strip):
#   Current session
#   ████████████   24% used
#   Resets 11:19am (Asia/Calcutta)
#
#   Current week (all models)
#   ██████████████   84% used
#   Resets Jul 24 at 2:29am (Asia/Calcutta)
# ---------------------------------------------------------------------------

_CL_SESSION_RE = re.compile(
    r"Current\s+session.*?(\d+)%\s+used.*?Resets\s+([^\n\r]+)",
    re.DOTALL | re.IGNORECASE,
)
_CL_WEEKLY_RE = re.compile(
    r"Current\s+week.*?(\d+)%\s+used.*?Resets\s+([^\n\r]+)",
    re.DOTALL | re.IGNORECASE,
)


def parse_claude_usage(text: str) -> Optional[dict]:
    """Parse Claude /usage output; return dict or None on failure.

    Never raises — any parse failure returns None.
    """
    try:
        clean = _strip_ansi(text)
        ms = _CL_SESSION_RE.search(clean)
        mw = _CL_WEEKLY_RE.search(clean)
        if not ms or not mw:
            return None
        return {
            "session_pct_used": int(ms.group(1)),
            "session_resets_at": ms.group(2).strip(),
            "weekly_pct_used": int(mw.group(1)),
            "weekly_resets_at": mw.group(2).strip(),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Gemini /usage parser
#
# Expected output (after ANSI strip):
#   Weekly Limit   30.13%   30% remaining · Refreshes in 89h 27m
#   Five Hour Limit  31.22%  31% remaining · Refreshes in 3h 7m
#
# The separator before "Refreshes" may be · (U+00B7) or • (U+2022).
# ---------------------------------------------------------------------------

_GEM_WEEKLY_RE = re.compile(
    r"Weekly\s+Limit\s+([\d.]+)%.*?Refreshes\s+in\s+([^\n\r]+)",
    re.IGNORECASE,
)
_GEM_5HR_RE = re.compile(
    r"Five\s+Hour\s+Limit\s+([\d.]+)%.*?Refreshes\s+in\s+([^\n\r]+)",
    re.IGNORECASE,
)


def parse_gemini_usage(text: str) -> Optional[dict]:
    """Parse Gemini /usage output; return dict or None on failure.

    Never raises — any parse failure returns None.
    """
    try:
        clean = _strip_ansi(text)
        mw = _GEM_WEEKLY_RE.search(clean)
        m5 = _GEM_5HR_RE.search(clean)
        if not mw or not m5:
            return None
        return {
            "weekly_pct_used": float(mw.group(1)),
            "weekly_refreshes_in": mw.group(2).strip(),
            "fivehr_pct_used": float(m5.group(1)),
            "fivehr_refreshes_in": m5.group(2).strip(),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PTY capture + provider dispatch
# ---------------------------------------------------------------------------


def capture_provider_usage(wrapper, timeout: float = 2.0) -> Optional[dict]:
    """Inject /usage into the PTY and parse the response by provider.

    Skips silently when ``ANTHROPIC_API_KEY`` is set (API-key mode has no
    interactive /usage command).  Returns parsed dict or None; never raises.

    Parameters
    ----------
    wrapper:
        PTYWrapper instance with ``write_input(str)`` and ``master_fd`` (int).
    timeout:
        Maximum seconds to wait for PTY output.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return None  # API-key mode — /usage is a Claude Code CLI command only

    # Detect provider from wrapper command list
    cmd = getattr(wrapper, "_command", None) or []
    cmd0 = (cmd[0] if isinstance(cmd, list) and cmd else str(cmd or ""))
    provider = os.path.basename(str(cmd0)).lower()

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
            except OSError:
                break

        text = b"".join(chunks).decode("utf-8", errors="replace")
        if "gemini" in provider or "aistudio" in provider:
            return parse_gemini_usage(text)
        return parse_claude_usage(text)
    except Exception:
        return None

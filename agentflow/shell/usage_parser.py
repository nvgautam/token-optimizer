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
# Claude /cost parser
#
# Expected output (after ANSI strip):
#   Total cost:  $0.2467
#   ...
#   Input:  5,234 tokens ($0.0157)
#   Output:  1,234 tokens ($0.0741)
#   ...
# ---------------------------------------------------------------------------

_CL_COST_TOTAL_RE = re.compile(
    r"[Tt]otal\s+cost\s*[:\s]\s*\$\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)
_CL_COST_INPUT_RE = re.compile(
    r"[Ii]nput\s*[:\s]\s*([\d,]+)\s+tokens?",
    re.IGNORECASE,
)
_CL_COST_OUTPUT_RE = re.compile(
    r"[Oo]utput\s*[:\s]\s*([\d,]+)\s+tokens?",
    re.IGNORECASE,
)


def parse_claude_cost(text: str) -> Optional[dict]:
    """Parse Claude /cost output; return dict or None on failure.

    Extracts total_cost_usd and optional token counts.
    Never raises — any parse failure returns None.
    """
    try:
        clean = _strip_ansi(text)
        mt = _CL_COST_TOTAL_RE.search(clean)
        if not mt:
            return None
        result: dict = {
            "total_cost_usd": float(mt.group(1).replace(",", "")),
        }
        mi = _CL_COST_INPUT_RE.search(clean)
        if mi:
            result["input_tokens"] = int(mi.group(1).replace(",", ""))
        mo = _CL_COST_OUTPUT_RE.search(clean)
        if mo:
            result["output_tokens"] = int(mo.group(1).replace(",", ""))
        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PTY capture + provider dispatch
# ---------------------------------------------------------------------------


def capture_provider_usage(wrapper, timeout: float = 2.0) -> Optional[dict]:
    """Inject /cost into the PTY and parse the response by provider.

    Works in both API-key mode (ANTHROPIC_API_KEY set) and OAuth mode
    because /cost is available in both.  Returns parsed dict or None; never raises.

    Parameters
    ----------
    wrapper:
        PTYWrapper instance with ``write_input(str)`` and ``master_fd`` (int).
    timeout:
        Maximum seconds to wait for PTY output.
    """
    # Detect provider from wrapper command list
    cmd = getattr(wrapper, "_command", None) or []
    cmd0 = (cmd[0] if isinstance(cmd, list) and cmd else str(cmd or ""))
    provider = os.path.basename(str(cmd0)).lower()

    try:
        wrapper.write_input("/cost\r")
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
        return parse_claude_cost(text)
    except Exception:
        return None

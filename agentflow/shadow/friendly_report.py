"""Aggregate-only savings dashboard for AgentFlow users.

No strategy-level breakdown is exposed (no targeted_reads / verbosity /
headroom / no_reread labels).  Uses a triangular-sum approximation to
estimate tokens saved from context recycling.
"""
from __future__ import annotations

import json
from pathlib import Path

SONNET_INPUT_RATE: float = 3.0 / 1_000_000  # USD per input token
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _session_savings(session: dict) -> int:
    """Return estimated tokens saved for a single closed session."""
    cap = session.get("cap_5hr") or 0
    start_pct = session.get("start_pct_5hr")
    end_pct = session.get("end_pct_5hr")
    detail = session.get("token_detail") or {}
    n_turns: int = int(detail.get("n_turns") or 0)
    final_ctx: int = int(detail.get("final_ctx") or 0)

    # Determine tokens_consumed from pct fields when available
    tokens_consumed: float = 0.0
    if start_pct is not None and end_pct is not None and cap:
        delta = float(end_pct) - float(start_pct)
        if delta < 0:
            # Session crossed the 100 % reset boundary
            delta = (100.0 - float(start_pct)) + float(end_pct)
        tokens_consumed = delta / 100.0 * cap
    elif final_ctx:
        tokens_consumed = float(final_ctx)

    # Average context over the session lifetime
    avg_ctx: float = float(final_ctx) if final_ctx else (tokens_consumed or 50_000.0)

    # Without recycling each turn would accumulate: sum(1..n)*avg_ctx / n ≈ n*avg_ctx/2
    waste_tokens: float = n_turns * avg_ctx / 2.0

    return int(max(0.0, waste_tokens - tokens_consumed))


def compute_friendly_report(ledger_path: Path) -> dict:
    """Return aggregate savings metrics from the AgentFlow ledger.

    Keys returned:
        session_count  int
        tokens_saved   int   — estimated from context recycling
        usd_saved      float — tokens_saved * SONNET_INPUT_RATE
        sessions       list[{"session_idx": int, "tokens_saved": int}]
    """
    try:
        raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"session_count": 0, "tokens_saved": 0, "usd_saved": 0.0, "sessions": []}

    closed = [s for s in (raw.get("sessions") or []) if s.get("status") == "closed"]

    per_session = []
    total_saved = 0
    for idx, sess in enumerate(closed):
        saved = _session_savings(sess)
        per_session.append({"session_idx": idx, "tokens_saved": saved})
        total_saved += saved

    return {
        "session_count": len(closed),
        "tokens_saved": total_saved,
        "usd_saved": round(total_saved * SONNET_INPUT_RATE, 6),
        "sessions": per_session,
    }


def _sparkline(values: list[int]) -> str:
    """Return an ASCII sparkline string, one character per value."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    chars = []
    for v in values:
        idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
        chars.append(_SPARK_CHARS[idx])
    return "".join(chars)


def render_text_report(report: dict) -> str:
    """Render the friendly report as a human-readable string."""
    lines = [
        "AgentFlow Savings Summary",
        "=========================",
        f"Sessions:       {report['session_count']:,}",
        f"Tokens saved:   {report['tokens_saved']:,}",
        f"USD saved:      ${report['usd_saved']:.2f}",
    ]

    per_session = report.get("sessions", [])
    if per_session:
        values = [s["tokens_saved"] for s in per_session]
        spark = _sparkline(values)
        lines.append("")
        lines.append("Session optimization (tokens saved per session):")
        lines.append(f"  {spark}")

    return "\n".join(lines)

"""T-087: steady-state (post-regression-fix) savings percentage.

report_builder.py's lifetime pct_saved blends the T-084 cache-mode
regression window (compression steady-state <1%) and the T-086
silent-headroom-off window (compression 0 for hours) in with everything
else -- both real degradations, not measurement bugs, so they cannot be
retroactively backfilled. That single blended number understates current
system capability for demo/investor use. This module isolates a second,
MEASURED (not modeled) figure: the same shadow-vs-real savings ratio
report_builder.py uses (total_saved / shadow_mode_tokens * 100), applied
only to closed agentflow_ledger.json sessions whose end_time falls at or
after the window start -- i.e. sessions closed after both fixes merged.

Each ledger session already carries its own shadow-mode baseline via
`shadow_event` (shadow_input/shadow_output), recorded alongside the real
input_tokens/output_tokens actually spent -- that pairing is the
per-session analogue of report_builder.py's shadow_mode_tokens vs
total_real split, so no new instrumentation is needed to compute this.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

# T-086 merge (PR #50) -- later than T-084's merge (PR #48, 2026-07-02T17:37:55Z).
WINDOW_START = "2026-07-02T21:24:05Z"


def _parse_ts(ts: str):
    """Same normalization as handoff_savings._parse_ts: mixed naive-local /
    UTC-'Z' / aware-offset timestamps -> aware UTC, or None if unparsable."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def compute_steady_state_pct_saved(sessions: list[dict], window_start: str = WINDOW_START) -> float | None:
    """Public contract: shadow-vs-real savings ratio (same formula as
    report_builder.py's lifetime pct_saved) over `sessions` whose end_time
    is at or after `window_start` (boundary inclusive). Returns None when
    no session in the window has usable shadow_event data -- callers must
    render "insufficient data yet" rather than a spurious 0%."""
    start_dt = _parse_ts(window_start)
    if start_dt is None:
        return None

    total_saved = 0
    shadow_mode_tokens = 0
    counted = 0
    for s in sessions:
        end_dt = _parse_ts(s.get("end_time", ""))
        if end_dt is None or end_dt < start_dt:
            continue
        shadow_event = s.get("shadow_event") or {}
        shadow_total = shadow_event.get("shadow_input", 0) + shadow_event.get("shadow_output", 0)
        if shadow_total <= 0:
            continue
        real_total = s.get("input_tokens", 0) + s.get("output_tokens", 0)
        counted += 1
        total_saved += max(0, shadow_total - real_total)
        shadow_mode_tokens += shadow_total

    if counted == 0 or shadow_mode_tokens <= 0:
        return None
    return (total_saved / shadow_mode_tokens) * 100


def _load_ledger_sessions(project_root: Path) -> list[dict]:
    path = project_root / "agentflow_ledger.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return [s for s in data.get("sessions", []) if s.get("status") == "closed"]


def load_steady_state_pct_saved(project_root: Path, window_start: str = WINDOW_START) -> dict:
    """Report-ready entry point (mirrors compute_handoff_savings' shape):
    loads closed sessions from agentflow_ledger.json, computes the
    window-filtered pct_saved, and returns it with an explicit measured
    (not modeled) methodology label."""
    sessions = _load_ledger_sessions(project_root)
    pct_saved = compute_steady_state_pct_saved(sessions, window_start)
    n_sessions = sum(
        1 for s in sessions
        if (end_dt := _parse_ts(s.get("end_time", ""))) is not None
        and end_dt >= _parse_ts(window_start)
        and (s.get("shadow_event") or {}).get("shadow_input", 0) + (s.get("shadow_event") or {}).get("shadow_output", 0) > 0
    )
    methodology = f"measured, sessions since {window_start} (post T-084/T-086 fixes), N={n_sessions}"
    return {"pct_saved": pct_saved, "n_sessions": n_sessions, "methodology": methodology}


def render_replacements(project_root: Path, window_start: str = WINDOW_START) -> dict:
    """Template-ready placeholder dict for combined_report.html -- keeps
    report_builder.py's wiring to a single spread-merge line."""
    result = load_steady_state_pct_saved(project_root, window_start)
    pct_str = "insufficient data yet" if result["pct_saved"] is None else f"{result['pct_saved']:.1f}%"
    return {
        "{steady_state_pct_str}": pct_str,
        "{steady_state_methodology_str}": result["methodology"],
    }

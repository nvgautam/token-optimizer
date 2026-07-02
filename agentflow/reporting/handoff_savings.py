"""T-085: calibrates the Handoff (context-cycling) triangular-sum savings
model from real closed sessions in agentflow_ledger.json, replacing
architecture.md's invented 500 tok/turn constant. See architecture.md
'### 1. Handoff (context cycling)' for the model this feeds.

This is a MODELED projection, not a directly-measured savings figure --
every value this module returns must carry the `methodology` label when
surfaced in a report (see report_builder.py wiring).
"""
import collections
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

THRESHOLD_TOKENS = 40_000   # architecture.md handoff trigger default
STATE_DOC_TOKENS = 3_500    # architecture.md: "~2-5K tokens" compact resume doc, midpoint
MATCH_WINDOW_SECONDS = 60   # session_type join tolerance (ledger end_time <-> telemetry handoff event)
MIN_MATCH_RATE = 0.5        # below this fraction, the session_type join is too unreliable to bucket by


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy 'linear' method), no numpy dep."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = (pct / 100) * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _parse_ts(ts: str):
    """Normalize mixed timestamp formats (naive local, UTC 'Z'-suffix, aware
    offset -- both agentflow_ledger.json end_time and telemetry.jsonl mix
    these) to aware UTC. Same class of fix as report_builder.py's
    _compression_delta_from_history (T-082)."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive -> assume local system time (ledger convention)
    return dt.astimezone(timezone.utc)


def _load_ledger_sessions(project_root: Path) -> list[dict]:
    path = project_root / "agentflow_ledger.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return [s for s in data.get("sessions", []) if s.get("status") == "closed"]


def _load_handoff_events(project_root: Path) -> list[tuple]:
    path = project_root / ".agentflow" / "telemetry.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("event") != "handoff":
            continue
        dt = _parse_ts(e.get("timestamp", ""))
        if dt is not None:
            events.append((dt, e.get("session_type")))
    events.sort(key=lambda p: p[0])
    return events


def _session_tok_per_turn(session: dict):
    td = session.get("token_detail", {})
    n = td.get("n_turns") or session.get("n_turns") or 0
    if not n:
        return None
    initial = td.get("initial_ctx")
    final = td.get("final_ctx", session.get("final_ctx"))
    if initial is None or final is None:
        return None
    return (final - initial) / n


def _bucket_sessions(sessions: list[dict], events: list[tuple]) -> tuple[dict, str]:
    """Join each session's end_time to the nearest handoff telemetry event
    (within MATCH_WINDOW_SECONDS) to recover session_type -- the ledger
    record itself does not carry it. Falls back to one unbucketed pool when
    fewer than MIN_MATCH_RATE of sessions get a confident match: on real
    project data telemetry.jsonl logs far fewer handoff events than there
    are closed ledger sessions, and matched timestamps are frequently
    minutes apart -- shipping that as reliable per-type bucketing would
    misattribute the majority of sessions (T-085)."""
    buckets: dict[str, list[float]] = {}
    turns: dict[str, list[int]] = {}
    matched = 0
    total = 0
    for s in sessions:
        rate = _session_tok_per_turn(s)
        if rate is None:
            continue
        total += 1
        n_turns = s.get("token_detail", {}).get("n_turns") or s.get("n_turns") or 0
        bucket = "unknown"
        end_dt = _parse_ts(s.get("end_time", ""))
        if end_dt is not None and events:
            nearest_dt, stype = min(events, key=lambda e: abs((e[0] - end_dt).total_seconds()))
            if abs((nearest_dt - end_dt).total_seconds()) <= MATCH_WINDOW_SECONDS and stype:
                bucket = stype
                matched += 1
        buckets.setdefault(bucket, []).append(rate)
        turns.setdefault(bucket, []).append(n_turns)

    if total == 0 or matched / total < MIN_MATCH_RATE:
        all_rates = [r for v in buckets.values() for r in v]
        all_turns = [t for v in turns.values() for t in v]
        return {"unbucketed": {"rates": all_rates, "turns": all_turns}}, "unbucketed"
    return {k: {"rates": buckets[k], "turns": turns[k]} for k in buckets}, "bucketed"


def _tag_breakdown_note(events: list[tuple]) -> str:
    """Population-level signal for the unbucketed case: even when the
    per-session join is too unreliable to trust (_bucket_sessions), the
    handoff events themselves still carry session_type -- report which type
    dominates the tagged population instead of a bare "no join" note."""
    tags = [t for _, t in events if t]
    if not tags:
        return "unbucketed -- no reliable session_type join"
    dominant, n = collections.Counter(tags).most_common(1)[0]
    return f"predominantly {dominant} sessions ({n} of {len(tags)} tagged handoff events)"


def _triangular_sum(tok_per_turn: float, n_turns: int) -> float:
    return tok_per_turn * n_turns * (n_turns + 1) / 2


def _project_session(tok_per_turn: float, n_turns: int) -> dict:
    """Triangular-sum handoff model (architecture.md '### 1. Handoff'):
    input cost compounds because each turn resends all prior context. A
    handoff fired once accumulated context crosses THRESHOLD_TOKENS flushes
    to a STATE_DOC_TOKENS-sized resume doc instead of letting context keep
    compounding for the rest of the session."""
    empty = {"baseline_tokens": 0.0, "with_handoff_tokens": 0.0, "tokens_saved": 0, "pct_reduction": 0.0, "handoff_turn": 0}
    if tok_per_turn <= 0 or n_turns <= 0:
        return empty

    baseline = _triangular_sum(tok_per_turn, n_turns)
    handoff_turn = max(1, min(n_turns - 1, int(THRESHOLD_TOKENS / tok_per_turn))) if n_turns > 1 else 0
    if handoff_turn <= 0:
        # Session never crosses the threshold -- no handoff would fire.
        return {**empty, "baseline_tokens": baseline, "with_handoff_tokens": baseline}

    remaining = n_turns - handoff_turn
    with_handoff = _triangular_sum(tok_per_turn, handoff_turn) + STATE_DOC_TOKENS * remaining + _triangular_sum(tok_per_turn, remaining)
    saved = max(0.0, baseline - with_handoff)
    pct = (saved / baseline * 100) if baseline else 0.0
    return {"baseline_tokens": baseline, "with_handoff_tokens": with_handoff, "tokens_saved": int(saved), "pct_reduction": pct, "handoff_turn": handoff_turn}


def compute_handoff_savings(project_root: Path) -> dict:
    """Public entry point: calibrates tok/turn from agentflow_ledger.json,
    projects triangular-sum handoff savings for a representative (median
    measured length) session, and returns a report-ready dict including an
    explicit methodology label. Never presented as directly measured."""
    sessions = _load_ledger_sessions(project_root)
    events = _load_handoff_events(project_root)
    bucketed, mode = _bucket_sessions(sessions, events)

    if not bucketed or not any(b["rates"] for b in bucketed.values()):
        return {"tokens_saved": 0, "pct_reduction": 0.0, "n_sessions": 0, "tok_per_turn": 0.0, "mode": mode,
                "methodology": "modeled from N=0 measured sessions -- no closed sessions in agentflow_ledger.json"}

    # Real data (T-085 spike) always lands in "unbucketed": telemetry.jsonl
    # logs far fewer handoff events than closed ledger sessions, and matched
    # timestamps are frequently minutes apart -- see _bucket_sessions. When
    # bucketing IS reliable, use the largest bucket (most-represented
    # session type) as the calibration source for the single headline figure.
    primary_key = max(bucketed, key=lambda k: len(bucketed[k]["rates"]))
    rates = bucketed[primary_key]["rates"]
    turns = bucketed[primary_key]["turns"]

    tok_per_turn = _percentile(rates, 25)
    n_sessions = len(rates)
    rep_n_turns = int(statistics.median(turns)) if turns else 0

    projection = _project_session(tok_per_turn, rep_n_turns)

    bucket_note = _tag_breakdown_note(events) if mode == "unbucketed" else f"bucket={primary_key}"
    methodology = (
        f"modeled from N={n_sessions} measured sessions ({bucket_note}), "
        f"p25 conservative percentile ({tok_per_turn:.0f} tok/turn), triangular-sum projection"
    )

    return {
        "tokens_saved": projection["tokens_saved"],
        "pct_reduction": projection["pct_reduction"],
        "n_sessions": n_sessions,
        "tok_per_turn": tok_per_turn,
        "mode": mode,
        "methodology": methodology,
    }

import json
from datetime import datetime, timezone
from pathlib import Path
from agentflow.reporting.steady_state import _parse_ts, WINDOW_START


def _reporting_window(entries: list[dict]) -> tuple[str, str] | None:
    ts = [e.get("ts") for e in entries if e.get("ts")]
    return (min(ts), max(ts)) if ts else None


def _filter_by_window(entries: list[dict], w: tuple[str, str] | None) -> list[dict]:
    if w:
        return [e for e in entries if w[0] <= e.get("ts", "") <= w[1]]
    return entries


def _load_proxy_log(project_root: Path) -> int:
    """Sum tokens saved from agentflow's own proxy_log.jsonl."""
    path = project_root / ".agentflow" / "proxy_log.jsonl"
    if not path.exists():
        return 0
    saved = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            saved += e.get("tokens_before", 0) - e.get("tokens_after", 0)
    except Exception:
        pass
    return max(0, saved)


def _load_proxy_savings(project_root: Path) -> dict | None:
    candidates = [
        project_root / ".headroom" / "proxy_savings.json",
        Path.home() / ".headroom" / "proxy_savings.json",
    ]
    try:
        from headroom import paths as _hr_paths
        candidates.insert(0, Path(_hr_paths.savings_path()))
    except Exception:
        pass
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                continue
    return None


def _compression_delta_from_history(history: list[dict], window: tuple[str, str] | None, field: str) -> int:
    parsed = []
    for e in history:
        try:
            parsed.append((datetime.fromisoformat(e.get("timestamp", "").replace("Z", "+00:00")), e))
        except ValueError:
            continue
    if not parsed:
        return 0
    parsed.sort(key=lambda p: p[0])
    if window is None:
        return parsed[-1][1].get(field, 0)
    start_dt, end_dt = (datetime.fromisoformat(w).astimezone(timezone.utc) for w in window)
    end_val = start_val = 0
    for dt, e in parsed:
        if dt < start_dt:
            start_val = e.get(field, 0)
        if dt <= end_dt:
            end_val = e.get(field, 0)
    return max(0, end_val - start_val)


def _format_baseline_annotation(baseline: dict) -> str:
    if not baseline.get("measured"):
        return f" [UNMEASURED baseline={baseline.get('baseline_tokens', 0)}tok, n=0 -- run T-081 A/B comparison]"
    n, ci_low, ci_high = baseline.get("sample_size", 0), baseline.get("ci95_low"), baseline.get("ci95_high")
    ci_str = f"95% CI [{ci_low:.0f}, {ci_high:.0f}]" if (ci_low is not None and ci_high is not None) else "CI unavailable (n<2)"
    return f" [measured baseline={baseline.get('baseline_tokens', 0)}tok, n={n}, {ci_str}]"


def _handoff_component(project_root: Path, window_start: str = WINDOW_START) -> tuple[int, int, int]:
    try:
        sessions = json.loads((project_root / "agentflow_ledger.json").read_text()).get("sessions", [])
    except Exception:
        return (0, 0, 0)
    start_dt = _parse_ts(window_start)
    if not start_dt:
        return (0, 0, 0)
    saved = real = n = 0
    for s in [x for x in sessions if x.get("status") == "closed" and _parse_ts(x.get("end_time", "")) and _parse_ts(x.get("end_time", "")) >= start_dt]:
        se = s.get("shadow_event") or {}
        shadow = se.get("shadow_input", 0) + se.get("shadow_output", 0)
        if shadow > 0:
            real_i = s.get("input_tokens", 0) + s.get("output_tokens", 0)
            saved += max(0, shadow - real_i)
            real += real_i
            n += 1
    return (saved, real, n)


def _lifetime_recycling_callout(project_root: Path) -> tuple[int, int, int]:
    try:
        sessions = json.loads((project_root / "agentflow_ledger.json").read_text()).get("sessions", [])
    except Exception:
        return (0, 0, 0)
    cl = [s for s in sessions if s.get("status") == "closed"]
    return (sum((s.get("shadow_event") or {}).get("shadow_extra", 0) for s in cl),
            sum(s.get("input_tokens", 0) + s.get("output_tokens", 0) for s in cl), len(cl))


def _load_calibration_html() -> str:
    cal_dir = Path.home() / ".agentflow"
    cards = []
    for agent in ["claude", "gemini"]:
        path = cal_dir / f"rate_calibration_{agent}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    ewma = data.get("ewma_pct_per_task")
                    rem = data.get("tasks_remaining")
                    if ewma is not None or rem is not None:
                        ewma_str = f"{ewma:.2f}%" if isinstance(ewma, (int, float)) else "N/A"
                        rem_str = f"{rem}" if rem is not None else "N/A"
                        cards.append(f"""
            <div class="card">
                <div class="stat-label">Capacity Calibration ({agent.capitalize()})</div>
                <div class="stat-value" style="font-size: 1.8rem; color: #a78bfa;">{rem_str} tasks remaining</div>
                <div class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">EWMA per task: {ewma_str}</div>
            </div>""")
            except Exception:
                pass
    return "".join(cards)

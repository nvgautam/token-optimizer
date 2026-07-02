import json
from datetime import datetime, timezone
from pathlib import Path
from agentflow.shadow.analyzer import _load_log, get_bucketed_stats
from agentflow.shadow.verbosity_ab import load_baseline
from agentflow.reporting import handoff_savings, steady_state


def _reporting_window(entries: list[dict]) -> tuple[str, str] | None:
    """Timestamp range covered by `entries` (shadow_reads.jsonl, the
    current-scope log). Returns None when there's no timestamped data to
    bound the window with — callers should treat that as "no window
    constraint" rather than an empty window."""
    ts_values = [e.get("ts") for e in entries if e.get("ts")]
    if not ts_values:
        return None
    return (min(ts_values), max(ts_values))


def _filter_by_window(entries: list[dict], window: tuple[str, str] | None) -> list[dict]:
    """T-081: verbosity_log.jsonl accumulates for the project's lifetime
    while shadow_reads.jsonl is scoped to the current reporting run. Summing
    the former unfiltered against the latter double-counts history that
    isn't part of this report. Bound verbosity entries to the same window."""
    if window is None:
        return entries
    start, end = window
    return [e for e in entries if start <= e.get("ts", "") <= end]


def _load_proxy_savings(project_root: Path) -> dict | None:
    """T-082: headroom-ai writes telemetry here, not headroom.db (SQLite),
    whose get_summary_stats() returns all-zero counts against live data."""
    path = project_root / ".headroom" / "proxy_savings.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _compression_delta_from_history(history: list[dict], window: tuple[str, str] | None, field: str) -> int:
    """Snapshots of a cumulative counter, not per-event deltas: contribution
    = value at window end minus value before window start (0 baseline if
    none precedes -- never fabricated). window=None => latest vs 0.
    history timestamps are UTC ("...Z"); window bounds are naive *local*
    (shadow_reads.jsonl/verbosity_log.jsonl use datetime.now(), no offset)
    -- raw string-compare across the two silently misattributes entries
    whenever local != UTC (T-082); parse+normalize to UTC instead."""
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
    # naive local -> aware local -> UTC (astimezone() presumes system tz).
    start_dt, end_dt = (datetime.fromisoformat(w).astimezone(timezone.utc) for w in window)
    end_val = start_val = 0
    for dt, e in parsed:
        if dt < start_dt:
            start_val = e.get(field, 0)
        if dt <= end_dt:
            end_val = e.get(field, 0)
    return max(0, end_val - start_val)


def _format_baseline_annotation(baseline: dict) -> str:
    """Sample size + CI alongside the verbosity savings figure so a
    small-sample (or absent) A/B baseline isn't presented as precise."""
    if not baseline.get("measured"):
        return f" [UNMEASURED baseline={baseline.get('baseline_tokens', 0)}tok, n=0 -- run T-081 A/B comparison]"
    n = baseline.get("sample_size", 0)
    ci_low = baseline.get("ci95_low")
    ci_high = baseline.get("ci95_high")
    if ci_low is not None and ci_high is not None:
        ci_str = f"95% CI [{ci_low:.0f}, {ci_high:.0f}]"
    else:
        ci_str = "CI unavailable (n<2)"
    return f" [measured baseline={baseline.get('baseline_tokens', 0)}tok, n={n}, {ci_str}]"


def build_report(project_root: Path, mode: str = "aggregate", output_path: str = "combined_report.html", store_url: str = None) -> int:
    if store_url is None:
        local_db = project_root / ".headroom" / "headroom.db"
        store_url = f"sqlite:///{local_db.resolve()}" if local_db.exists() else f"sqlite:///{Path.home()}/.headroom/headroom.db"

    log_path = project_root / ".agentflow" / "shadow_reads.jsonl"
    raw_entries = _load_log(log_path) if log_path.exists() else []

    # Blocked attempts (idx exists, offset=None) never executed the read --
    # left in, they'd double-count as phantom real cost + phantom savings.
    entries = [e for e in raw_entries if not (e.get("offset") is None and bool(e.get("idx_exists")) and (e.get("idx_sections") or 0) > 0)]

    reads_files = set()
    tasks_path = project_root / "tasks.json"
    if tasks_path.exists():
        try:
            data = json.loads(tasks_path.read_text())
            for t in data.get("tasks", []):
                for r in t.get("reads", []):
                    reads_files.add(r.split("#")[0])
        except Exception:
            pass

    stats = get_bucketed_stats(project_root, entries, reads_files, mode=mode)

    verb_log_path = project_root / ".agentflow" / "verbosity_log.jsonl"
    verb_entries = []
    if verb_log_path.exists():
        try:
            for line in verb_log_path.read_text().splitlines():
                if line.strip():
                    verb_entries.append(json.loads(line))
        except Exception:
            pass

    # T-081: window verbosity to entries' scope; use the measured baseline.
    reporting_window = _reporting_window(entries)
    windowed_verb_entries = _filter_by_window(verb_entries, reporting_window)
    verbosity_baseline = load_baseline(project_root)
    baseline_tokens = verbosity_baseline.get("baseline_tokens", 600)
    verbosity_savings = sum(max(0, baseline_tokens - e.get("output_tokens", 0)) for e in windowed_verb_entries)
    verbosity_annotation = _format_baseline_annotation(verbosity_baseline)

    proxy_savings = _load_proxy_savings(project_root)  # T-082: compression from proxy_savings.json, windowed like verbosity.
    history = (proxy_savings or {}).get("history", [])
    compression_savings = _compression_delta_from_history(history, reporting_window, "total_tokens_saved")
    compression_real = _compression_delta_from_history(history, reporting_window, "total_input_tokens")

    headroom_html, headroom_installed = "", False
    try:
        from headroom.storage import create_storage
        from headroom.reporting.generator import generate_report

        try:
            storage = create_storage(store_url)
            storage.get_summary_stats()  # presence check only; compression figures come from proxy_savings.json
            headroom_installed = True
        except Exception:
            pass

        if headroom_installed:
            temp_path = project_root / ".agentflow" / "temp_headroom.html"
            try:
                generate_report(store_url, str(temp_path))
                if temp_path.exists():
                    headroom_html = temp_path.read_text(encoding="utf-8")
                    temp_path.unlink()
            except Exception:
                pass
    except ImportError:
        pass

    shadow_sum = sum(stats.values())

    file_reads_real = file_reads_baseline = 0
    for e in entries:
        offset = e.get("offset")
        limit = e.get("limit")
        file_lines = e.get("file_lines", 0)
        file_chars = e.get("file_chars", 0)
        idx_sections = e.get("idx_sections", 0)

        baseline = int(file_chars * 0.25)
        if offset is not None:
            if file_lines > 0 and limit is not None:
                real = int(file_chars * (limit / file_lines) * 0.25)
            else:
                sections = max(1, idx_sections)
                real = int(file_chars / sections * 0.25)
            real = min(baseline, real)
        else:
            real = baseline
        file_reads_real += real
        file_reads_baseline += baseline

    # shadow_sum is a waste metric; real savings = baseline minus actual cost.
    file_reads_saved = file_reads_baseline - file_reads_real
    total_saved = file_reads_saved + verbosity_savings + compression_savings

    # Same window as verbosity_savings -- cost and savings must match scope.
    verbosity_real = sum(e.get("output_tokens", 0) for e in windowed_verb_entries)

    if compression_real == 0:
        # No measured "after" cost -- exclude compression rather than guess.
        compression_savings = 0

    total_real = file_reads_real + verbosity_real + compression_real
    shadow_mode_tokens = total_real + total_saved
    pct_saved = (total_saved / shadow_mode_tokens * 100) if shadow_mode_tokens > 0 else 0.0

    print("\n==============================================")
    print("       AgentFlow Savings Report Summary")
    print("==============================================")
    print(f"Mode: {mode}")
    print("----------------------------------------------")
    suffix = " (aggregate)" if mode != "aggregate" else ""
    print(f"TOTAL TOKENS SAVED{suffix}:      {total_saved:,} tokens")
    print(f"REAL TOKENS USED{suffix}:        {total_real:,} tokens")
    print(f"SHADOW MODE TOKENS (baseline{suffix}): {shadow_mode_tokens:,} tokens")
    print(f"PERCENTAGE SAVED{suffix}:        {pct_saved:.1f}%")
    # T-083: waste (lower=better) vs real savings; state-docs is a volume figure, not savings.
    STRATEGY_ROWS = [
        ("stats_idx", "Symbol Index & Section loading (idx)", "waste", stats["targeted-reads"], ""),
        ("stats_no_reread", "No-re-read Rule compliance (no-reread)", "waste", stats["no-reread"], ""),
        ("stats_indexing_gap", "Indexing Gap avoidance (indexing-gap)", "waste", stats["indexing-gap"], ""),
        ("stats_state_docs", "Compact State Documents — read volume, not savings (state-docs)", "real", stats["state-docs"], ""),
        ("verbosity_savings", "Output Verbosity Savings (verbosity)", "real", verbosity_savings, verbosity_annotation),
        ("compression_savings", "Compression Savings (compression)", "real", compression_savings, ""),
        ("handoff_savings", "Session Recycling — Handoff/context cycling, MODELED not measured (handoff)", "modeled", (_hs := handoff_savings.compute_handoff_savings(project_root))["tokens_saved"], f" [{_hs['methodology']}]"),
    ]
    if mode != "aggregate":
        for section, header in (("waste", "Waste Avoided (shadow, lower is better)"), ("real", f"Real Savings Realized (total_saved={total_saved:,} tokens)"), ("modeled", "Modeled Projections (not measured -- see methodology per row)")):
            print(f"----------------------------------------------\n{header}")
            for _, label, sec, val, note in STRATEGY_ROWS:
                if sec == section:
                    print(f"  {label}: {val:,} tokens{note}")
        print("----------------------------------------------")
        print("Note: Summing waste-avoided values directly may double-count overlaps.")

    print(f"Verbosity baseline (T-081):{verbosity_annotation}")

    template_path = Path(__file__).parent / "dashboard_template.html"
    html_template = template_path.read_text(encoding="utf-8")

    headroom_section_html = f'<div class="headroom-section"><h2>Headroom Deep Analytics</h2>{headroom_html}</div>' if headroom_html else ''

    replacements = {
        "{mode_upper}": mode.upper(),
        "{total_saved_str}": f"{total_saved:,}",
        "{total_real_str}": f"{total_real:,}",
        "{shadow_mode_tokens_str}": f"{shadow_mode_tokens:,}",
        "{pct_saved_str}": f"{pct_saved:.1f}",
        "{shadow_sum_str}": f"{shadow_sum:,}",
        "{headroom_section_html}": headroom_section_html,
        **steady_state.render_replacements(project_root),  # T-087: steady-state pct_saved, post T-084/T-086.
    }
    replacements.update({f"{{{ph}_str}}": f"{val:,}{note}" for ph, _, _, val, note in STRATEGY_ROWS})
    for k, v in replacements.items():
        html_template = html_template.replace(k, v)
    out_path = Path(output_path)
    out_path.write_text(html_template, encoding="utf-8")
    print(f"\nHTML Report written to: {out_path.resolve()}")
    return 0

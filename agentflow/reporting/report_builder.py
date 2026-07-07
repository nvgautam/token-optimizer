import json
from datetime import datetime, timezone
from pathlib import Path
from agentflow.shadow.analyzer import _load_log, get_bucketed_stats
from agentflow.shadow.verbosity_ab import load_baseline, import_from_verbosity_log, run_ab_comparison
from agentflow.reporting.steady_state import _parse_ts, WINDOW_START
from agentflow.reporting import growth_tracker, code_size_savings

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

def build_report(project_root: Path, mode: str = "aggregate", output_path: str = "combined_report.html", store_url: str = None) -> int:
    try:
        import_from_verbosity_log(project_root)
        run_ab_comparison(project_root)
    except Exception:
        pass
    if store_url is None:
        local_db = project_root / ".headroom" / "headroom.db"
        store_url = f"sqlite:///{local_db.resolve()}" if local_db.exists() else f"sqlite:///{Path.home()}/.headroom/headroom.db"
    _all_raw = _load_log(project_root / ".agentflow" / "shadow_reads.jsonl") if (project_root / ".agentflow" / "shadow_reads.jsonl").exists() else []
    entries = [e for e in _all_raw if (ts := _parse_ts(e.get("ts", ""))) and ts >= _parse_ts(WINDOW_START) and not (e.get("offset") is None and bool(e.get("idx_exists")) and (e.get("idx_sections") or 0) > 0)]
    all_shadow_entries = [e for e in _all_raw if not (e.get("offset") is None and bool(e.get("idx_exists")) and (e.get("idx_sections") or 0) > 0)]
    reads_files = set()
    try:
        data = json.loads((project_root / "tasks.json").read_text())
        reads_files.update(r.split("#")[0] for t in data.get("tasks", []) for r in t.get("reads", []))
    except Exception:
        pass
    stats = get_bucketed_stats(project_root, entries, reads_files, mode=mode)
    verb_entries = []
    if (project_root / ".agentflow" / "verbosity_log.jsonl").exists():
        try:
            verb_entries = [json.loads(line) for line in (project_root / ".agentflow" / "verbosity_log.jsonl").read_text().splitlines() if line.strip()]
        except Exception:
            pass
    windowed_verb_entries = _filter_by_window(verb_entries, _reporting_window(entries))
    verbosity_baseline = load_baseline(project_root)
    baseline_tokens = verbosity_baseline.get("baseline_tokens", 600)
    verbosity_savings = sum(max(0, baseline_tokens - e.get("output_tokens", 0)) for e in windowed_verb_entries)
    verbosity_annotation = _format_baseline_annotation(verbosity_baseline)
    stopping_met = verbosity_baseline.get("stopping_met", False)
    stopping_status = verbosity_baseline.get("stopping_status", "")
    history = (_load_proxy_savings(project_root) or {}).get("history", [])
    compression_savings = _compression_delta_from_history(history, _reporting_window(entries), "total_tokens_saved")
    if compression_savings == 0:
        compression_savings = _load_proxy_log(project_root)
    if compression_savings == 0:
        try:
            from headroom import savings_ledger as _sl
            _report = _sl.aggregate_savings()
            compression_savings = _report.lifetime.get("tokens_saved", 0)
        except Exception:
            pass
    headroom_html = ""
    try:
        from headroom.storage import create_storage
        from headroom.reporting.generator import generate_report
        storage = create_storage(store_url)
        storage.get_summary_stats()
        temp_path = project_root / ".agentflow" / "temp_headroom.html"
        generate_report(store_url, str(temp_path))
        if temp_path.exists():
            headroom_html = temp_path.read_text(encoding="utf-8")
            temp_path.unlink()
    except (ImportError, Exception):
        pass
    shadow_sum = sum(stats.values())
    _all_stats = growth_tracker.compute_file_read_stats(all_shadow_entries)
    _win_stats = growth_tracker.compute_file_read_stats(entries)
    idx_savings, offset_savings, file_reads_real = _all_stats["idx_savings"], _all_stats["offset_savings"], _win_stats["file_reads_real"]
    _families = code_size_savings.load_file_families(project_root / ".agentflow" / "file_families.jsonl")
    code_size_saved = code_size_savings.compute_code_size_savings(all_shadow_entries, _families)["total_saved_tokens"]
    _cs_by_date = {e["date"]: e["code_size"] for e in code_size_savings.daily_code_size_savings(all_shadow_entries, _families)}
    daily = growth_tracker.daily_savings(all_shadow_entries, project_root / ".agentflow" / "proxy_log.jsonl", windowed_verb_entries, baseline_tokens, code_size_by_date=_cs_by_date)
    proj = growth_tracker.projections(daily)
    file_reads_saved = idx_savings + offset_savings
    handoff_saved, handoff_real, n_sessions = _handoff_component(project_root)
    total_saved = file_reads_saved + verbosity_savings + handoff_saved + compression_savings + code_size_saved
    total_real = file_reads_real + sum(e.get("output_tokens", 0) for e in windowed_verb_entries) + handoff_real
    shadow_mode_tokens = total_real + total_saved
    pct_saved = (total_saved / shadow_mode_tokens * 100) if shadow_mode_tokens > 0 else 0.0
    print(f"\nAGENTFLOW SAVINGS ({mode}): {pct_saved:.1f}% | {total_saved:,} saved / {shadow_mode_tokens:,} shadow")
    print(f"HANDOFF COMPONENT (N={n_sessions} sessions): {handoff_saved:,} saved from {handoff_real:,} real")
    shadow_extra_all, real_all, n_all = _lifetime_recycling_callout(project_root)
    lifetime_recycle_pct = (shadow_extra_all / (shadow_extra_all + real_all) * 100) if (shadow_extra_all + real_all) > 0 else 0.0
    print(f"LIFETIME RECYCLING (N={n_all} sessions): {lifetime_recycle_pct:.1f}% vs shadow baseline (no-recycle model)")
    denom = idx_savings + compression_savings + verbosity_savings + handoff_saved + code_size_saved
    def pct(val):
        return (val / denom * 100) if denom > 0 else 0.0
    idx_savings_pct, verbosity_savings_pct, compression_savings_pct, handoff_savings_pct, code_size_savings_pct = pct(idx_savings), pct(verbosity_savings), pct(compression_savings), pct(handoff_saved), pct(code_size_saved)
    STRATEGY_ROWS = [
        ("stats_idx", "Symbol Index & Section loading (idx)", "waste", stats["targeted-reads"], ""),
        ("stats_no_reread", "No-re-read Rule compliance (no-reread)", "waste", stats["no-reread"], ""),
        ("stats_indexing_gap", "Indexing Gap avoidance (indexing-gap)", "waste", stats["indexing-gap"], ""),
        ("idx_savings", "Targeted Reads — Savings Realized (idx)", "real", idx_savings, ""),
        ("stats_state_docs", "Compact State Documents — read volume, not savings (state-docs)", "real", stats["state-docs"], ""),
        ("verbosity_savings", "Output Verbosity Savings (verbosity)", "real", verbosity_savings, verbosity_annotation),
        ("compression_savings", "Compression Savings (compression)", "real", compression_savings, ""),
        ("handoff_savings", "Session Recycling — measured from agentflow_ledger.json (handoff)", "real", handoff_saved, f" [windowed N={n_sessions} sessions since WINDOW_START]"),
        ("code_size_savings", "Code-Size Savings via file splitting (code-size)", "real", code_size_saved, "")
    ]
    print(f"Verbosity baseline (T-081):{verbosity_annotation}")
    print(f"Verbosity A/B stopping criterion status: {stopping_status}")
    html_template = (Path(__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")
    html_template = html_template.replace(
        '            <div class="card">\n                <div class="stat-label">Compression Savings</div>\n                <div class="stat-value">{compression_savings_str}</div>\n                <div class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Headroom context reduction</div>\n            </div>',
        '            <div class="card">\n                <div class="stat-label">Compression Savings</div>\n                <div class="stat-value">{compression_savings_str}</div>\n                <div class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Headroom context reduction</div>\n            </div>\n            {capacity_calibration_html}'
    )
    headroom_section_html = f'<div class="headroom-section"><h2>Headroom Deep Analytics</h2>{headroom_html}</div>' if headroom_html else ''
    banner_style = "background: rgba(16, 185, 129, 0.1); border: 1px solid var(--success); color: var(--success);" if stopping_met else "background: rgba(245, 158, 11, 0.1); border: 1px solid #f59e0b; color: #f59e0b;"
    banner_icon = "✓" if stopping_met else "⚠"
    banner_html = f'<div class="verbosity-ab-banner" style="{banner_style} border-radius: 12px; padding: 1rem 1.5rem; margin-bottom: 2rem; display: flex; align-items: center; justify-content: space-between; font-weight: 500;"><span style="display: flex; align-items: center; gap: 0.5rem;"><span style="font-size: 1.2rem;">{banner_icon}</span>{stopping_status}</span></div>'
    replacements = {
        "{mode_upper}": mode.upper(), "{total_saved_str}": f"{total_saved:,}", "{total_real_str}": f"{total_real:,}",
        "{shadow_mode_tokens_str}": f"{shadow_mode_tokens:,}", "{pct_saved_str}": f"{pct_saved:.1f}",
        "{shadow_sum_str}": f"{shadow_sum:,}", "{headroom_section_html}": headroom_section_html,
        "{steady_state_pct_str}": f"{compression_savings:,} tokens",
        "{steady_state_methodology_str}": "Headroom compression; windowed to shadow-reads scope — included in combined %",
        "{lifetime_recycling_str}": f"Lifetime (N={n_all} sessions) — {lifetime_recycle_pct:.1f}% vs shadow baseline (no-recycle model)",
        "{idx_savings_pct}": f"{idx_savings_pct:.1f}", "{verbosity_savings_pct}": f"{verbosity_savings_pct:.1f}",
        "{compression_savings_pct}": f"{compression_savings_pct:.1f}", "{handoff_savings_pct}": f"{handoff_savings_pct:.1f}",
        "{code_size_savings_pct}": f"{code_size_savings_pct:.1f}", "{verbosity_ab_banner_html}": banner_html, "{capacity_calibration_html}": _load_calibration_html()
    }
    replacements.update({f"{{{ph}_str}}": f"{val:,}{note}" for ph, _, _, val, note in STRATEGY_ROWS})
    replacements["{trend_panel_html}"] = growth_tracker.render_sparklines_html(daily)
    replacements["{projection_table_html}"] = growth_tracker.render_projection_table_html(proj)
    for k, v in replacements.items():
        html_template = html_template.replace(k, v)
    out_path = Path(output_path)
    out_path.write_text(html_template, encoding="utf-8")
    print(f"\nHTML Report written to: {out_path.resolve()}")
    return 0

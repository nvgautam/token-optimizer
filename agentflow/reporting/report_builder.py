import json
from pathlib import Path
from agentflow.shadow.analyzer import _load_log, get_bucketed_stats
from agentflow.shadow.verbosity_ab import load_baseline, import_from_verbosity_log, run_ab_comparison
from agentflow.reporting.steady_state import _parse_ts, WINDOW_START
from agentflow.reporting import growth_tracker, code_size_savings
from agentflow.reporting.model_routing import model_routing_savings
from agentflow.reporting.report_builder_helpers import (
    _reporting_window,
    _filter_by_window,
    _load_proxy_log,
    _load_proxy_savings,
    _compression_delta_from_history,
    _format_baseline_annotation,
    _handoff_component,
    _lifetime_recycling_callout,
    _load_calibration_html,
)

# Re-export helpers for backward compatibility
__all__ = [
    'build_report',
    '_reporting_window',
    '_filter_by_window',
    '_load_proxy_log',
    '_load_proxy_savings',
    '_compression_delta_from_history',
    '_format_baseline_annotation',
    '_handoff_component',
    '_lifetime_recycling_callout',
    '_load_calibration_html',
]


def build_report(project_root: Path, mode: str = "aggregate", output_path: str = "combined_report.html", store_url: str = None) -> int:
    try:
        import_from_verbosity_log(project_root)
        run_ab_comparison(project_root)
    except Exception:
        pass
    try:
        from agentflow.shadow.model_ab import run_model_ab
        _model_ab = run_model_ab(project_root)
    except Exception:
        _model_ab = {}
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
    verbosity_savings_per_turn = verbosity_baseline.get("verbosity_savings_per_turn", 0.0)
    verbosity_pct_saved = verbosity_baseline.get("verbosity_pct_saved", 0.0)
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
    routing = model_routing_savings(project_root)
    routing_usd, routing_tasks, routing_tokens = routing["usd_saved"], routing["haiku_tasks"], routing["token_saved_equivalent"]
    total_saved = file_reads_saved + verbosity_savings + handoff_saved + compression_savings + code_size_saved + routing_tokens
    total_real = file_reads_real + sum(e.get("output_tokens", 0) for e in windowed_verb_entries) + handoff_real
    shadow_mode_tokens = total_real + total_saved
    pct_saved = (total_saved / shadow_mode_tokens * 100) if shadow_mode_tokens > 0 else 0.0
    print(f"\nAGENTFLOW SAVINGS ({mode}): {pct_saved:.1f}% | {total_saved:,} saved / {shadow_mode_tokens:,} shadow")
    print(f"HANDOFF COMPONENT (N={n_sessions} sessions): {handoff_saved:,} saved from {handoff_real:,} real")
    shadow_extra_all, real_all, n_all = _lifetime_recycling_callout(project_root)
    lifetime_recycle_pct = (shadow_extra_all / (shadow_extra_all + real_all) * 100) if (shadow_extra_all + real_all) > 0 else 0.0
    print(f"LIFETIME RECYCLING (N={n_all} sessions): {lifetime_recycle_pct:.1f}% vs shadow baseline (no-recycle model)")
    denom = idx_savings + compression_savings + verbosity_savings + handoff_saved + code_size_saved + routing_tokens
    def pct(val):
        return (val / denom * 100) if denom > 0 else 0.0
    idx_savings_pct, verbosity_savings_pct, compression_savings_pct, handoff_savings_pct, code_size_savings_pct, routing_savings_pct = pct(idx_savings), pct(verbosity_savings), pct(compression_savings), pct(handoff_saved), pct(code_size_saved), pct(routing_tokens)
    STRATEGY_ROWS = [
        ("stats_idx", "Symbol Index & Section loading (idx)", "waste", stats["targeted-reads"], ""),
        ("stats_no_reread", "No-re-read Rule compliance (no-reread)", "waste", stats["no-reread"], ""),
        ("stats_indexing_gap", "Indexing Gap avoidance (indexing-gap)", "waste", stats["indexing-gap"], ""),
        ("idx_savings", "Targeted Reads — Savings Realized (idx)", "real", idx_savings, ""),
        ("stats_state_docs", "Compact State Documents — read volume, not savings (state-docs)", "real", stats["state-docs"], ""),
        ("verbosity_savings", "Output Verbosity Savings (verbosity)", "real", verbosity_savings, verbosity_annotation),
        ("compression_savings", "Compression Savings (compression)", "real", compression_savings, ""),
        ("handoff_savings", "Session Recycling — measured from agentflow_ledger.json (handoff)", "real", handoff_saved, f" [windowed N={n_sessions} sessions since WINDOW_START]"),
        ("code_size_savings", "Code-Size Savings via file splitting (code-size)", "real", code_size_saved, ""),
        ("model_routing_savings", f"Model Routing — Haiku vs Sonnet ({routing_tasks} tasks, ${routing_usd:.4f} USD saved) (model-routing)", "real", routing_tokens, f" [${routing_usd:.4f} USD saved, token-equivalent at output price]"),
    ]
    print(f"Verbosity baseline (T-081):{verbosity_annotation}")
    print(f"  Per-turn savings: {verbosity_savings_per_turn:.1f} tokens/turn ({verbosity_pct_saved:.1f}% of output tokens)")
    print(f"Verbosity A/B stopping criterion status: {stopping_status}")
    _mab_models = _model_ab.get("models", {})
    _h_n = _mab_models.get("haiku", {}).get("n", 0)
    _s_n = _mab_models.get("sonnet", {}).get("n", 0)
    if _h_n >= 5 and _s_n >= 5:
        print(f"MODEL ROUTING A/B: haiku mean={_mab_models['haiku']['mean']:.1f} sonnet mean={_mab_models['sonnet']['mean']:.1f} delta={_model_ab.get('delta_pct', 0.0):.1f}%")
    else:
        print(f"MODEL ROUTING A/B: insufficient data (haiku n={_h_n}, sonnet n={_s_n}, need 5 each)")
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
        "{code_size_savings_pct}": f"{code_size_savings_pct:.1f}", "{model_routing_savings_pct}": f"{routing_savings_pct:.1f}",
        "{verbosity_ab_banner_html}": banner_html, "{capacity_calibration_html}": _load_calibration_html()
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

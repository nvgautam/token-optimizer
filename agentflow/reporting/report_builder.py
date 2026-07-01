import json
from pathlib import Path
from agentflow.shadow.analyzer import _load_log, get_bucketed_stats


def build_report(project_root: Path, mode: str = "aggregate", output_path: str = "combined_report.html", store_url: str = None) -> int:
    if store_url is None:
        local_db = project_root / ".headroom" / "headroom.db"
        if local_db.exists():
            store_url = f"sqlite:///{local_db.resolve()}"
        else:
            store_url = f"sqlite:///{Path.home()}/.headroom/headroom.db"

    log_path = project_root / ".agentflow" / "shadow_reads.jsonl"
    entries = _load_log(log_path) if log_path.exists() else []

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
    verbosity_savings = 0
    if verb_log_path.exists():
        try:
            verb_entries = []
            for line in verb_log_path.read_text().splitlines():
                if line.strip():
                    verb_entries.append(json.loads(line))
            verbosity_savings = sum(max(0, 600 - e.get("output_tokens", 0)) for e in verb_entries)
        except Exception:
            pass

    compression_savings = 0
    headroom_html = ""
    headroom_installed = False

    try:
        from headroom.storage import create_storage
        from headroom.reporting.generator import generate_report

        try:
            storage = create_storage(store_url)
            stats_hr = storage.get_summary_stats()
            compression_savings = stats_hr.get("total_tokens_saved", 0)
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
    total_saved = shadow_sum + verbosity_savings + compression_savings

    file_reads_real = 0
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

    verbosity_real = 0
    if verb_log_path.exists():
        try:
            verbosity_real = sum(e.get("output_tokens", 0) for e in verb_entries)
        except Exception:
            pass

    compression_real = 0
    if headroom_installed:
        try:
            compression_real = stats_hr.get("total_tokens_after", stats_hr.get("after_tokens", 0))
            if compression_real == 0 and compression_savings > 0:
                compression_real = 15000
        except Exception:
            pass

    total_real = file_reads_real + verbosity_real + compression_real
    shadow_mode_tokens = total_real + total_saved
    pct_saved = (total_saved / shadow_mode_tokens * 100) if shadow_mode_tokens > 0 else 0.0

    print("\n==============================================")
    print("       AgentFlow Savings Report Summary")
    print("==============================================")
    print(f"Mode: {mode}")
    print("----------------------------------------------")
    if mode == "aggregate":
        print(f"TOTAL TOKENS SAVED:                           {total_saved:,} tokens")
        print(f"REAL TOKENS USED:                             {total_real:,} tokens")
        print(f"SHADOW MODE TOKENS (baseline):                {shadow_mode_tokens:,} tokens")
        print(f"PERCENTAGE SAVED:                             {pct_saved:.1f}%")
    else:
        print(f"TOTAL TOKENS SAVED (aggregate):                {total_saved:,} tokens")
        print(f"REAL TOKENS USED (aggregate):                  {total_real:,} tokens")
        print(f"SHADOW MODE TOKENS (baseline aggregate):       {shadow_mode_tokens:,} tokens")
        print(f"PERCENTAGE SAVED (aggregate):                  {pct_saved:.1f}%")
        print("----------------------------------------------")
        print(f"Symbol Index & Section loading (idx):         {stats['targeted-reads']:,} tokens")
        print(f"No-re-read Rule compliance (no-reread):       {stats['no-reread']:,} tokens")
        print(f"Indexing Gap reduction (indexing-gap):         {stats['indexing-gap']:,} tokens")
        print(f"Compact State Documents (state-docs):          {stats['state-docs']:,} tokens")
        print(f"Output Verbosity Savings (verbosity):         {verbosity_savings:,} tokens")
        print(f"Compression Savings (compression):            {compression_savings:,} tokens")
        print("----------------------------------------------")
        print("Note: Summing these values directly may double-count overlaps.")

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
        "{compression_savings_str}": f"{compression_savings:,}",
        "{stats_idx_str}": f"{stats['targeted-reads']:,}",
        "{stats_no_reread_str}": f"{stats['no-reread']:,}",
        "{stats_indexing_gap_str}": f"{stats['indexing-gap']:,}",
        "{stats_state_docs_str}": f"{stats['state-docs']:,}",
        "{verbosity_savings_str}": f"{verbosity_savings:,}",
        "{headroom_section_html}": headroom_section_html,
    }
    for k, v in replacements.items():
        html_template = html_template.replace(k, v)

    out_path = Path(output_path)
    out_path.write_text(html_template, encoding="utf-8")
    print(f"\nHTML Report written to: {out_path.resolve()}")
    return 0

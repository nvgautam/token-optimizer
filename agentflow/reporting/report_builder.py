import json
from pathlib import Path
from agentflow.shadow.analyzer import _load_log, get_bucketed_stats
from agentflow.shadow.verbosity_ab import load_baseline


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
        if local_db.exists():
            store_url = f"sqlite:///{local_db.resolve()}"
        else:
            store_url = f"sqlite:///{Path.home()}/.headroom/headroom.db"

    log_path = project_root / ".agentflow" / "shadow_reads.jsonl"
    raw_entries = _load_log(log_path) if log_path.exists() else []

    # read_logger.py fires as a PreToolUse hook alongside read_check.py, so it logs
    # every attempted Read *before* read_check decides to block it. Rows with an
    # existing non-empty .idx and offset=None are exactly the ones read_check.py
    # rejects (exit 2) — the read never executed, so they carry zero real cost and
    # zero realized savings. Left in, they get double-counted: once as phantom
    # "real" full-read cost below, once as phantom "targeted-read" savings via
    # get_bucketed_stats.
    def _is_blocked_attempt(e: dict) -> bool:
        return (
            e.get("offset") is None
            and bool(e.get("idx_exists"))
            and (e.get("idx_sections") or 0) > 0
        )

    entries = [e for e in raw_entries if not _is_blocked_attempt(e)]

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

    # T-081: align the verbosity reporting window to the same window as
    # `entries` (shadow_reads.jsonl, current-scope) before mixing the two
    # into total_saved, and use the measured hook-off baseline instead of
    # the unvalidated 600-token design estimate.
    windowed_verb_entries = _filter_by_window(verb_entries, _reporting_window(entries))
    verbosity_baseline = load_baseline(project_root)
    baseline_tokens = verbosity_baseline.get("baseline_tokens", 600)
    verbosity_savings = sum(max(0, baseline_tokens - e.get("output_tokens", 0)) for e in windowed_verb_entries)
    verbosity_annotation = _format_baseline_annotation(verbosity_baseline)

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

    file_reads_real = 0
    file_reads_baseline = 0
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

    # shadow_sum (from get_bucketed_stats) counts full/non-targeted reads — i.e.
    # opportunities NOT taken (violations, indexing gaps). That's a waste metric,
    # not tokens actually saved; folding it into total_saved is what inflated the
    # headline percentage. Real savings = baseline cost minus what was actually
    # spent, on reads that actually happened.
    file_reads_saved = file_reads_baseline - file_reads_real
    total_saved = file_reads_saved + verbosity_savings + compression_savings

    # Same window as verbosity_savings above -- real cost and savings must be
    # scoped identically or shadow_mode_tokens/pct_saved get skewed.
    verbosity_real = sum(e.get("output_tokens", 0) for e in windowed_verb_entries)

    compression_real = 0
    if headroom_installed:
        try:
            compression_real = stats_hr.get("total_tokens_after", stats_hr.get("after_tokens", 0))
        except Exception:
            pass
        if compression_real == 0:
            # No measured "after" cost to divide against — don't fabricate a
            # denominator. Exclude compression from the totals rather than guess.
            compression_savings = 0

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
        print(f"Output Verbosity Savings (verbosity):         {verbosity_savings:,} tokens{verbosity_annotation}")
        print(f"Compression Savings (compression):            {compression_savings:,} tokens")
        print("----------------------------------------------")
        print("Note: Summing these values directly may double-count overlaps.")

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
        "{compression_savings_str}": f"{compression_savings:,}",
        "{stats_idx_str}": f"{stats['targeted-reads']:,}",
        "{stats_no_reread_str}": f"{stats['no-reread']:,}",
        "{stats_indexing_gap_str}": f"{stats['indexing-gap']:,}",
        "{stats_state_docs_str}": f"{stats['state-docs']:,}",
        "{verbosity_savings_str}": f"{verbosity_savings:,}{verbosity_annotation}",
        "{headroom_section_html}": headroom_section_html,
    }
    for k, v in replacements.items():
        html_template = html_template.replace(k, v)

    out_path = Path(output_path)
    out_path.write_text(html_template, encoding="utf-8")
    print(f"\nHTML Report written to: {out_path.resolve()}")
    return 0

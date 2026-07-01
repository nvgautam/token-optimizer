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

    print("\n==============================================")
    print("       AgentFlow Savings Report Summary")
    print("==============================================")
    print(f"Mode: {mode}")
    print("----------------------------------------------")
    if mode == "aggregate":
        print(f"Non-overlapping Token Savings (Log Analysis): {shadow_sum:,} tokens")
        print(f"Output Verbosity Savings:                     {verbosity_savings:,} tokens")
        print(f"Compression Savings (Headroom):               {compression_savings:,} tokens")
        print("----------------------------------------------")
        print(f"TOTAL TOKENS SAVED:                           {total_saved:,} tokens")
    else:
        print(f"Symbol Index & Section loading (idx):         {stats['targeted-reads']:,} tokens")
        print(f"No-re-read Rule compliance:                   {stats['no-reread']:,} tokens")
        print(f"Indexing Gap reduction:                       {stats['indexing-gap']:,} tokens")
        print(f"Compact State Documents:                      {stats['state-docs']:,} tokens")
        print(f"Output Verbosity Savings:                     {verbosity_savings:,} tokens")
        print(f"Compression Savings (Headroom):               {compression_savings:,} tokens")
        print("----------------------------------------------")
        print("Note: Summing these values directly may double-count overlaps.")

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentFlow Token Savings Dashboard</title>
    <style>
        :root {{ --bg-color: #0b0f19; --card-bg: rgba(255, 255, 255, 0.03); --border-color: rgba(255, 255, 255, 0.08); --primary: #4f46e5; --primary-glow: rgba(79, 70, 229, 0.4); --success: #10b981; --text-main: #f3f4f6; --text-muted: #9ca3af; }}
        body {{ background-color: var(--bg-color); color: var(--text-main); font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 2rem; min-height: 100vh; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{ margin-bottom: 3rem; text-align: center; position: relative; }}
        h1 {{ font-size: 2.8rem; margin: 0; background: linear-gradient(135deg, #a78bfa 0%, #4f46e5 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; letter-spacing: -0.025em; }}
        .subtitle {{ color: var(--text-muted); font-size: 1.1rem; margin-top: 0.5rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 3rem; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 16px; padding: 1.5rem; backdrop-filter: blur(12px); transition: transform 0.3s ease, border-color 0.3s ease; }}
        .card:hover {{ transform: translateY(-4px); border-color: rgba(79, 70, 229, 0.3); }}
        .stat-value {{ font-size: 2.2rem; font-weight: 700; color: var(--success); margin: 0.5rem 0; }}
        .stat-label {{ font-size: 0.9rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
        .details-section {{ margin-top: 3rem; border-top: 1px solid var(--border-color); padding-top: 2rem; }}
        .strategy-row {{ display: flex; justify-content: space-between; padding: 1rem 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }}
        .headroom-section {{ margin-top: 4rem; background: rgba(255, 255, 255, 0.02); border-radius: 16px; padding: 2rem; border: 1px solid var(--border-color); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>AgentFlow Token Savings</h1>
            <p class="subtitle">Real-time token optimization & waste analytics • Mode: {mode.upper()}</p>
        </header>

        <div class="grid">
            <div class="card">
                <div class="stat-label">Total Tokens Saved</div>
                <div class="stat-value">{total_saved:,}</div>
                <div class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Cumulative optimization savings</div>
            </div>
            <div class="card">
                <div class="stat-label">Shadow Cost Avoided</div>
                <div class="stat-value">{shadow_sum:,}</div>
                <div class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Avoided file I/O waste</div>
            </div>
            <div class="card">
                <div class="stat-label">Compression Savings</div>
                <div class="stat-value">{compression_savings:,}</div>
                <div class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Headroom context reduction</div>
            </div>
        </div>

        <div class="details-section">
            <h2>Savings Breakdown by Strategy</h2>
            <div class="strategy-row">
                <span>Symbol Index / Targeted Reads (idx)</span>
                <strong>{stats['targeted-reads']:,} tokens</strong>
            </div>
            <div class="strategy-row">
                <span>No-re-read Rule Compliance (no-reread)</span>
                <strong>{stats['no-reread']:,} tokens</strong>
            </div>
            <div class="strategy-row">
                <span>Indexing Gap Avoidance (indexing-gap)</span>
                <strong>{stats['indexing-gap']:,} tokens</strong>
            </div>
            <div class="strategy-row">
                <span>Compact State Documents (state-docs)</span>
                <strong>{stats['state-docs']:,} tokens</strong>
            </div>
            <div class="strategy-row">
                <span>Output Verbosity Control (verbosity)</span>
                <strong>{verbosity_savings:,} tokens</strong>
            </div>
            <div class="strategy-row">
                <span>Headroom Compression (compression)</span>
                <strong>{compression_savings:,} tokens</strong>
            </div>
        </div>

        {f'<div class="headroom-section"><h2>Headroom Deep Analytics</h2>{headroom_html}</div>' if headroom_html else ''}
    </div>
</body>
</html>
"""

    out_path = Path(output_path)
    out_path.write_text(html_template, encoding="utf-8")
    print(f"\nHTML Report written to: {out_path.resolve()}")
    return 0

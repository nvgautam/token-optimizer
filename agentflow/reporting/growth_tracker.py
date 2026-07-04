"""Daily savings aggregation and 30-day projection for the dashboard."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import json

IDX_OPTIMISTIC_MULTIPLIER = 2.0  # 90% compliance vs ~45% current ≈ 2x uplift
CODE_SIZE_OPTIMISTIC_MULTIPLIER = 1.5  # more splits over time

_STRATEGIES = ("idx", "compression", "verbosity", "code_size")


def _entry_idx_saved(e: dict) -> int:
    """Tokens saved by this shadow_reads entry (0 if not idx-driven)."""
    if not bool(e.get("idx_exists")):
        return 0
    file_chars = e.get("file_chars", 0)
    file_lines = e.get("file_lines", 0)
    idx_sections = e.get("idx_sections", 0)
    offset = e.get("offset")
    limit = e.get("limit")
    baseline = int(file_chars * 0.25)
    if offset is not None:
        if file_lines > 0 and limit is not None:
            real = int(file_chars * (limit / file_lines) * 0.25)
        else:
            real = int(file_chars / max(1, idx_sections) * 0.25)
        real = min(baseline, real)
    else:
        real = baseline
    return baseline - real


def compute_file_read_stats(entries: list[dict]) -> dict:
    """Return idx_savings, offset_savings, file_reads_real, file_reads_baseline."""
    idx_savings = offset_savings = 0
    file_reads_real = file_reads_baseline = 0
    for e in entries:
        file_chars = e.get("file_chars", 0)
        file_lines = e.get("file_lines", 0)
        idx_sections = e.get("idx_sections", 0)
        idx_exists = bool(e.get("idx_exists"))
        offset = e.get("offset")
        limit = e.get("limit")
        baseline = int(file_chars * 0.25)
        if offset is not None:
            if file_lines > 0 and limit is not None:
                real = int(file_chars * (limit / file_lines) * 0.25)
            else:
                real = int(file_chars / max(1, idx_sections) * 0.25)
            real = min(baseline, real)
        else:
            real = baseline
        file_reads_real += real
        file_reads_baseline += baseline
        saved = baseline - real
        if idx_exists:
            idx_savings += saved
        else:
            offset_savings += saved
    return {
        "idx_savings": idx_savings,
        "offset_savings": offset_savings,
        "file_reads_real": file_reads_real,
        "file_reads_baseline": file_reads_baseline,
    }


def _date_str(ts: str) -> str:
    """Extract YYYY-MM-DD from a timestamp string."""
    return ts[:10] if ts else ""


def daily_savings(
    shadow_entries: list[dict],
    proxy_log_path: Path,
    verb_entries: list[dict],
    baseline_tokens: int,
    days: int = 14,
    code_size_by_date: dict[str, int] | None = None,
) -> list[dict]:
    """Return list of {date, idx, compression, verbosity} dicts for last `days` days."""
    idx_by_date: dict[str, int] = defaultdict(int)
    for e in shadow_entries:
        d = _date_str(e.get("ts", ""))
        if d:
            idx_by_date[d] += _entry_idx_saved(e)

    comp_by_date: dict[str, int] = defaultdict(int)
    if proxy_log_path and proxy_log_path.exists():
        try:
            for line in proxy_log_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    d = _date_str(entry.get("ts", ""))
                    if d:
                        saved = max(0, entry.get("tokens_before", 0) - entry.get("tokens_after", 0))
                        comp_by_date[d] += saved
                except Exception:
                    continue
        except Exception:
            pass

    verb_by_date: dict[str, int] = defaultdict(int)
    for e in verb_entries:
        d = _date_str(e.get("ts", ""))
        if d:
            verb_by_date[d] += max(0, baseline_tokens - e.get("output_tokens", 0))

    cs = code_size_by_date or {}
    all_dates = sorted(set(list(idx_by_date) + list(comp_by_date) + list(verb_by_date) + list(cs)))
    if not all_dates:
        return []

    return [
        {
            "date": d,
            "idx": idx_by_date[d],
            "compression": comp_by_date[d],
            "verbosity": verb_by_date[d],
            "code_size": cs.get(d, 0),
        }
        for d in all_dates[-days:]
    ]


def projections(daily: list[dict], horizon_days: int = 30) -> list[dict]:
    """Return list of {strategy, avg_per_day, base_30d, optimistic_30d} dicts.
    Uses 7-day rolling average of the last 7 days in `daily`.
    Optimistic: idx × IDX_OPTIMISTIC_MULTIPLIER, others unchanged."""
    last7 = daily[-7:] if len(daily) >= 7 else daily
    if not last7:
        return [
            {"strategy": s, "avg_per_day": 0.0, "base_30d": 0, "optimistic_30d": 0}
            for s in _STRATEGIES
        ]
    result = []
    for s in _STRATEGIES:
        avg = sum(d.get(s, 0) for d in last7) / len(last7)
        base = int(avg * horizon_days)
        if s == "idx":
            optimistic = int(avg * IDX_OPTIMISTIC_MULTIPLIER * horizon_days)
        elif s == "code_size":
            optimistic = int(avg * CODE_SIZE_OPTIMISTIC_MULTIPLIER * horizon_days)
        else:
            optimistic = base
        result.append({"strategy": s, "avg_per_day": round(avg, 1), "base_30d": base, "optimistic_30d": optimistic})
    return result


def _sparkline_svg(values: list[float], width: int = 120, height: int = 30, color: str = "#4f46e5") -> str:
    """Return inline SVG sparkline (width×height px). Pure polyline, no JS."""
    if not values or len(values) < 2:
        pts = f"0,{height} {width},{height}"
        return (
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/></svg>'
        )
    max_v = max(values)
    min_v = min(values)
    span = max_v - min_v if max_v != min_v else 1
    n = len(values)
    pad = 2
    pts_list = []
    for i, v in enumerate(values):
        x = pad + (i / (n - 1)) * (width - 2 * pad)
        y = (height - pad) - ((v - min_v) / span) * (height - 2 * pad)
        pts_list.append(f"{x:.1f},{y:.1f}")
    pts = " ".join(pts_list)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/></svg>'
    )


def render_sparklines_html(daily: list[dict]) -> str:
    """Return HTML with inline SVG sparklines (120×30px) per strategy.
    Pure SVG polylines — no JS, no CDN."""
    colors = {"idx": "#4f46e5", "compression": "#10b981", "verbosity": "#f59e0b", "code_size": "#e11d48"}
    labels = {"idx": "Symbol Index (idx)", "compression": "Compression", "verbosity": "Verbosity", "code_size": "Code Size (splits)"}
    rows = []
    for s in _STRATEGIES:
        values = [d.get(s, 0) for d in daily]
        svg = _sparkline_svg(values, color=colors.get(s, "#4f46e5"))
        rows.append(
            '<div style="display:flex;align-items:center;gap:1rem;padding:0.5rem 0;'
            'border-bottom:1px solid rgba(255,255,255,0.05);">'
            f'<span style="min-width:160px;font-size:0.9rem;">{labels[s]}</span>'
            f'{svg}</div>'
        )
    return "\n".join(rows)


def render_projection_table_html(proj: list[dict]) -> str:
    """Return an HTML <table> string for the projection section."""
    labels = {"idx": "Symbol Index (idx)", "compression": "Compression", "verbosity": "Verbosity", "code_size": "Code Size (splits)"}
    header = (
        '<thead><tr style="color:#9ca3af;">'
        '<th style="text-align:left;padding:0.4rem 0;">Strategy</th>'
        '<th style="text-align:right;padding:0.4rem 0;">7-day avg/day</th>'
        '<th style="text-align:right;padding:0.4rem 0;">30-day Base</th>'
        '<th style="text-align:right;padding:0.4rem 0;">30-day Optimistic</th>'
        '</tr></thead>'
    )
    body = ""
    for p in proj:
        lbl = labels.get(p["strategy"], p["strategy"])
        body += (
            f'<tr><td>{lbl}</td>'
            f'<td style="text-align:right">{p["avg_per_day"]:,.1f}</td>'
            f'<td style="text-align:right">{p["base_30d"]:,}</td>'
            f'<td style="text-align:right">{p["optimistic_30d"]:,}</td></tr>\n'
        )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:0.9rem;">'
        f'{header}<tbody>{body}</tbody></table>'
    )

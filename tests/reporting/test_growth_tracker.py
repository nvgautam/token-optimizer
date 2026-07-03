import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import pytest

from agentflow.reporting.growth_tracker import (
    daily_savings,
    projections,
    render_sparklines_html,
    render_projection_table_html,
    IDX_OPTIMISTIC_MULTIPLIER,
    compute_file_read_stats,
)


def _shadow(date_str: str, idx_exists: bool = True, file_chars: int = 1000,
            file_lines: int = 100, offset: int | None = None, limit: int = 20) -> dict:
    return {
        "ts": f"{date_str}T12:00:00",
        "idx_exists": idx_exists,
        "file_chars": file_chars,
        "file_lines": file_lines,
        "idx_sections": 3,
        "offset": offset,
        "limit": limit,
    }


# --------------------------------------------------------------------------- #
# daily_savings tests
# --------------------------------------------------------------------------- #

def test_daily_savings_empty(tmp_path):
    result = daily_savings([], tmp_path / "proxy_log.jsonl", [], 600)
    assert result == []


def test_daily_savings_groups_by_date(tmp_path):
    entries = [
        _shadow("2026-07-01", file_chars=4000, file_lines=100, offset=10, limit=20),
        _shadow("2026-07-01", file_chars=2000, file_lines=100, offset=0, limit=10),
        _shadow("2026-07-02", file_chars=3000, file_lines=100, offset=5, limit=20),
    ]
    result = daily_savings(entries, tmp_path / "missing.jsonl", [], 600)
    assert len(result) == 2
    dates = [r["date"] for r in result]
    assert "2026-07-01" in dates
    assert "2026-07-02" in dates
    july1 = next(r for r in result if r["date"] == "2026-07-01")
    july2 = next(r for r in result if r["date"] == "2026-07-02")
    assert july1["idx"] > 0
    assert july2["idx"] > 0
    # Two entries for July 1 → more idx savings than July 2's single entry
    assert july1["idx"] > july2["idx"]


def test_daily_savings_limits_to_days(tmp_path):
    base = datetime(2026, 6, 1)
    entries = [
        _shadow((base + timedelta(days=i)).strftime("%Y-%m-%d"), offset=10, limit=20)
        for i in range(20)
    ]
    result = daily_savings(entries, tmp_path / "missing.jsonl", [], 600, days=14)
    assert len(result) == 14
    assert result[0]["date"] == (base + timedelta(days=6)).strftime("%Y-%m-%d")
    assert result[-1]["date"] == (base + timedelta(days=19)).strftime("%Y-%m-%d")


def test_daily_savings_no_proxy_log(tmp_path):
    entries = [_shadow("2026-07-01", offset=10, limit=20)]
    result = daily_savings(entries, tmp_path / "nonexistent.jsonl", [], 600)
    assert len(result) == 1
    assert result[0]["compression"] == 0


# --------------------------------------------------------------------------- #
# projections tests
# --------------------------------------------------------------------------- #

def test_projections_uses_7day_avg():
    # Days 0-2: idx=0; days 3-9: idx=700 → last 7 days all 700
    daily = []
    for i in range(10):
        idx_val = 0 if i < 3 else 700
        daily.append({"date": f"2026-07-{i+1:02d}", "idx": idx_val, "compression": 0, "verbosity": 0})

    result = projections(daily)
    idx_proj = next(p for p in result if p["strategy"] == "idx")
    assert idx_proj["avg_per_day"] == pytest.approx(700.0, abs=0.1)
    assert idx_proj["base_30d"] == 700 * 30


def test_projections_optimistic_doubles_idx():
    daily = [{"date": f"2026-07-{i+1:02d}", "idx": 100, "compression": 50, "verbosity": 200} for i in range(7)]
    result = projections(daily)
    idx_proj = next(p for p in result if p["strategy"] == "idx")
    comp_proj = next(p for p in result if p["strategy"] == "compression")
    verb_proj = next(p for p in result if p["strategy"] == "verbosity")

    assert idx_proj["optimistic_30d"] == int(idx_proj["avg_per_day"] * IDX_OPTIMISTIC_MULTIPLIER * 30)
    # non-idx strategies: optimistic == base
    assert comp_proj["optimistic_30d"] == comp_proj["base_30d"]
    assert verb_proj["optimistic_30d"] == verb_proj["base_30d"]


# --------------------------------------------------------------------------- #
# rendering tests
# --------------------------------------------------------------------------- #

def test_render_sparklines_html_returns_svg():
    daily = [{"date": f"2026-07-{i+1:02d}", "idx": i * 10, "compression": i * 5, "verbosity": i * 3}
             for i in range(7)]
    html = render_sparklines_html(daily)
    assert "<svg" in html
    assert "polyline" in html


def test_render_projection_table_html_contains_rows():
    proj = [
        {"strategy": "idx", "avg_per_day": 100.0, "base_30d": 3000, "optimistic_30d": 6000},
        {"strategy": "compression", "avg_per_day": 50.0, "base_30d": 1500, "optimistic_30d": 1500},
        {"strategy": "verbosity", "avg_per_day": 200.0, "base_30d": 6000, "optimistic_30d": 6000},
    ]
    html = render_projection_table_html(proj)
    # header + 3 data rows = 4 <tr
    assert html.count("<tr") >= 3
    assert "6,000" in html

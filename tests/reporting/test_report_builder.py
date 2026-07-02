import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
from unittest.mock import MagicMock, patch
import argparse

from agentflow.shadow.analyzer import (
    _report_targeted_reads,
    _report_indexing_gap,
    _report_lazy_decomposition,
    _report_no_reread,
    _report_state_docs,
    _report_verbosity_compliance,
    main as analyzer_main
)
from agentflow.reporting.report_builder import (
    build_report,
    _reporting_window,
    _filter_by_window,
    _format_baseline_annotation,
    _load_proxy_savings,
    _compression_delta_from_history,
)
from agentflow.shadow.verbosity_ab import record_turn, run_ab_comparison
from agentflow.cli import cmd_report


def test_shadow_analyzer_bucketing(tmp_path):
    tasks_data = {"tasks": [{"task_id": "T-001", "reads": ["file_a.py", "file_b.py#anchor"]}]}
    (tmp_path / "tasks.json").write_text(json.dumps(tasks_data))

    entries = [
        # Double count candidate
        {"ts": "2026-07-01T12:00:00", "rel": "file_b.py", "offset": None, "idx_exists": True, "idx_sections": 4, "file_lines": 100, "file_chars": 4000},
        # Standard targeted hit
        {"ts": "2026-07-01T12:01:00", "rel": "file_c.py", "offset": 10, "idx_exists": True, "idx_sections": 5, "file_lines": 200, "file_chars": 8000},
        # Gap
        {"ts": "2026-07-01T12:02:00", "rel": "file_d.py", "offset": None, "idx_exists": False, "idx_sections": 0, "file_lines": 60, "file_chars": 2000},
        # State doc
        {"ts": "2026-07-01T12:03:00", "rel": "architecture.md", "offset": None, "idx_exists": False, "idx_sections": 0, "file_lines": 500, "file_chars": 10000},
    ]

    from agentflow.shadow.analyzer import get_bucketed_stats

    # Reads files should be {"file_a.py", "file_b.py"}
    reads_files = {"file_a.py", "file_b.py"}

    # aggregate: file_b.py matches no-reread. Value = 4000 * 0.25 = 1000.
    stats_agg = get_bucketed_stats(tmp_path, entries, reads_files, mode="aggregate")
    assert stats_agg["no-reread"] == 1000
    assert stats_agg["targeted-reads"] == 0
    assert stats_agg["indexing-gap"] == 500
    assert stats_agg["state-docs"] == 2500

    stats_by = get_bucketed_stats(tmp_path, entries, reads_files, mode="split")
    assert stats_by["no-reread"] == 1000
    assert stats_by["targeted-reads"] == 750
    assert stats_by["indexing-gap"] == 500
    assert stats_by["state-docs"] == 2500


def test_individual_reports(tmp_path):
    entries_empty = []
    assert _report_targeted_reads(entries_empty) == 0

    entries = [{"rel": "file_b.py", "offset": None, "idx_exists": True, "idx_sections": 4, "file_lines": 100, "file_chars": 4000}]
    assert _report_targeted_reads(entries) == 750

    assert _report_indexing_gap(entries_empty) == 0
    assert _report_indexing_gap(entries) == 0  # not gap because idx_exists=True
    entries_gap = [{"rel": "file_d.py", "offset": None, "idx_exists": False, "file_lines": 60, "file_chars": 2000}]
    assert _report_indexing_gap(entries_gap) == 500

    assert _report_lazy_decomposition(tmp_path) == 0
    tasks_data = {"tasks": [{"task_id": "T-001", "status": "complete"}, {"task_id": "T-002", "status": "pending", "reads": ["foo.py"]}]}
    (tmp_path / "tasks.json").write_text(json.dumps(tasks_data))
    assert _report_lazy_decomposition(tmp_path) > 0

    assert _report_no_reread(entries_empty, tmp_path) == 0
    entries_vio = [{"rel": "foo.py", "offset": None, "file_chars": 1200}]
    assert _report_no_reread(entries_vio, tmp_path) == 300

    (tmp_path / "architecture.md").write_text("Hello architecture")
    assert _report_state_docs(tmp_path) == 4

    assert _report_verbosity_compliance(tmp_path) == 0
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(json.dumps({"session_type": "oracle", "output_tokens": 100}) + "\n")
    assert _report_verbosity_compliance(tmp_path) == 500


def test_analyzer_main(tmp_path):
    log_path = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({"rel": "foo.py", "offset": None, "idx_exists": False, "file_lines": 60, "file_chars": 2000}) + "\n")
    (tmp_path / "tasks.json").write_text(json.dumps({"tasks": []}))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        analyzer_main()


def test_report_builder_integration(tmp_path):
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(
        json.dumps({"ts": "...", "session_type": "oracle", "turn": 1, "output_tokens": 120}) + "\n" +
        json.dumps({"ts": "...", "session_type": "oracle", "turn": 2, "output_tokens": 160}) + "\n"
    )

    # T-082: compression numbers come from proxy_savings.json, not the SQLite
    # mock. Window is None (no shadow_reads.jsonl) -> full unwindowed history
    # is used, i.e. the latest cumulative counter value.
    (tmp_path / ".headroom").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".headroom" / "proxy_savings.json").write_text(json.dumps({
        "history": [{"timestamp": "2026-07-01T10:00:00Z", "total_tokens_saved": 5000, "total_input_tokens": 15000}],
    }))

    # Mock headroom lib -- only used here for the separate deep-analytics HTML export.
    mock_headroom = MagicMock()
    mock_storage = MagicMock()
    mock_storage.get_summary_stats.return_value = {"total_tokens_saved": 0, "total_tokens_after": 0}
    mock_headroom.storage.create_storage.return_value = mock_storage

    def mock_gen(url, path):
        Path(path).write_text("Mocked Headroom Report Content")
    mock_headroom.reporting.generator.generate_report = mock_gen

    with patch.dict(sys.modules, {"headroom": mock_headroom, "headroom.storage": mock_headroom.storage, "headroom.reporting.generator": mock_headroom.reporting.generator}):
        out_html = tmp_path / "combined_report.html"
        build_report(project_root=tmp_path, mode="aggregate", output_path=out_html, store_url="sqlite:///dummy.db")

        assert out_html.exists()
        html_content = out_html.read_text()
        assert "aggregate" in html_content.lower()
        assert "5,000" in html_content
        assert "Mocked Headroom Report Content" in html_content
        assert "Real Tokens Used" in html_content
        assert "Shadow Mode Tokens" in html_content
        assert "Percentage Saved" in html_content

        build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
        assert out_html.exists()
        html_content_split = out_html.read_text()
        assert "Real Tokens Used" in html_content_split
        assert "Shadow Mode Tokens" in html_content_split
        assert "Percentage Saved" in html_content_split


def test_reporting_window_empty_entries():
    assert _reporting_window([]) is None
    assert _reporting_window([{"rel": "foo.py"}]) is None


def test_reporting_window_bounds_from_ts():
    entries = [{"ts": "2026-07-01T12:00:00"}, {"ts": "2026-07-01T09:00:00"}, {"ts": "2026-07-01T15:00:00"}]
    assert _reporting_window(entries) == ("2026-07-01T09:00:00", "2026-07-01T15:00:00")


def test_filter_by_window_none_returns_all():
    entries = [{"ts": "2026-07-01T12:00:00"}]
    assert _filter_by_window(entries, None) == entries


def test_filter_by_window_excludes_outside_range():
    entries = [
        {"ts": "2026-07-01T08:00:00", "output_tokens": 1},
        {"ts": "2026-07-01T12:00:00", "output_tokens": 2},
        {"ts": "2026-07-01T20:00:00", "output_tokens": 3},
    ]
    filtered = _filter_by_window(entries, ("2026-07-01T10:00:00", "2026-07-01T15:00:00"))
    assert [e["output_tokens"] for e in filtered] == [2]


def test_format_baseline_annotation_unmeasured():
    annotation = _format_baseline_annotation({"measured": False, "baseline_tokens": 600, "sample_size": 0})
    assert "UNMEASURED" in annotation
    assert "600" in annotation


def test_format_baseline_annotation_measured_with_ci():
    annotation = _format_baseline_annotation(
        {"measured": True, "baseline_tokens": 500, "sample_size": 10, "ci95_low": 450.0, "ci95_high": 550.0}
    )
    assert "measured" in annotation
    assert "n=10" in annotation
    assert "95% CI" in annotation
    assert "450" in annotation and "550" in annotation


def test_format_baseline_annotation_measured_single_sample_no_ci():
    annotation = _format_baseline_annotation(
        {"measured": True, "baseline_tokens": 500, "sample_size": 1, "ci95_low": None, "ci95_high": None}
    )
    assert "n=1" in annotation
    assert "CI unavailable" in annotation


def test_report_builder_uses_measured_baseline_not_hardcoded_600(tmp_path):
    # Seed a measured hook-off baseline of 500 tokens (n=3) via the T-081
    # A/B harness instead of the unvalidated 600-token design estimate.
    for tok in (400, 500, 600):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="hook_off")
    run_ab_comparison(tmp_path)

    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(json.dumps({"ts": "2026-07-01T12:00:00", "session_type": "oracle", "turn": 1, "output_tokens": 100}) + "\n")

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")

    html_content = out_html.read_text()
    # measured baseline (500) - 100 = 400, not the old 600 - 100 = 500
    assert "400" in html_content
    assert "measured baseline=500tok" in html_content
    assert "n=3" in html_content


def test_report_builder_falls_back_when_no_baseline_measured(tmp_path):
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(json.dumps({"ts": "2026-07-01T12:00:00", "session_type": "oracle", "turn": 1, "output_tokens": 100}) + "\n")

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")

    html_content = out_html.read_text()
    assert "UNMEASURED" in html_content
    assert "500" in html_content  # unmeasured fallback: 600 - 100 = 500


def test_report_builder_aligns_verbosity_window_to_shadow_reads_scope(tmp_path):
    shadow_log = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    shadow_log.parent.mkdir(parents=True, exist_ok=True)
    shadow_log.write_text(json.dumps({
        "ts": "2026-07-01T12:00:00", "rel": "foo.py", "offset": 1, "limit": 5,
        "idx_exists": True, "idx_sections": 2, "file_lines": 10, "file_chars": 400,
    }) + "\n")

    # One entry inside the window, one far outside (lifetime history) -- only
    # the in-window entry should count.
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.write_text(
        json.dumps({"ts": "2026-06-01T00:00:00", "session_type": "oracle", "turn": 1, "output_tokens": 0}) + "\n" +
        json.dumps({"ts": "2026-07-01T12:00:00", "session_type": "oracle", "turn": 2, "output_tokens": 100}) + "\n"
    )

    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()

    # Unmeasured baseline=600. In-window: 600-100=500. If the stale 600-0=600
    # entry leaked in, total would read 1,100.
    assert "500" in html_content
    assert "1,100" not in html_content


def test_cli_report_cmd(tmp_path):
    args = argparse.Namespace(mode="aggregate", output=str(tmp_path / "cli_report.html"))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        assert cmd_report(args) == 0
        assert (tmp_path / "cli_report.html").exists()


# --- T-082: compression data source (proxy_savings.json, not headroom.db) ---

def test_load_proxy_savings_absent_returns_none(tmp_path):
    assert _load_proxy_savings(tmp_path) is None


def test_load_proxy_savings_reads_json(tmp_path):
    (tmp_path / ".headroom").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".headroom" / "proxy_savings.json").write_text(json.dumps({"history": [{"timestamp": "t"}]}))
    assert _load_proxy_savings(tmp_path) == {"history": [{"timestamp": "t"}]}


def test_compression_delta_from_history_windowed():
    # Cumulative counters, not per-event increments: delta = end - baseline,
    # baseline being the last snapshot strictly before the window start.
    history = [
        {"timestamp": "2026-07-01T08:00:00Z", "total_tokens_saved": 1000, "total_input_tokens": 4000},
        {"timestamp": "2026-07-01T11:00:00Z", "total_tokens_saved": 1500, "total_input_tokens": 5000},
        {"timestamp": "2026-07-01T20:00:00Z", "total_tokens_saved": 3000, "total_input_tokens": 9000},
    ]
    window = ("2026-07-01T10:00:00", "2026-07-01T15:00:00")
    assert _compression_delta_from_history(history, window, "total_tokens_saved") == 500
    assert _compression_delta_from_history(history, window, "total_input_tokens") == 1000


def test_compression_delta_from_history_no_baseline_before_window():
    # Nothing precedes window start -> baseline is 0, never fabricated.
    history = [{"timestamp": "2026-07-01T12:00:00Z", "total_tokens_saved": 800, "total_input_tokens": 2000}]
    window = ("2026-07-01T10:00:00", "2026-07-01T15:00:00")
    assert _compression_delta_from_history(history, window, "total_tokens_saved") == 800


def test_compression_delta_from_history_empty_or_no_window():
    assert _compression_delta_from_history([], ("a", "b"), "total_tokens_saved") == 0
    assert _compression_delta_from_history([], None, "total_tokens_saved") == 0
    history = [{"timestamp": "2026-07-01T12:00:00Z", "total_tokens_saved": 42}]
    assert _compression_delta_from_history(history, None, "total_tokens_saved") == 42


def test_report_builder_windows_compression_to_shadow_reads_scope(tmp_path):
    shadow_log = tmp_path / ".agentflow" / "shadow_reads.jsonl"
    shadow_log.parent.mkdir(parents=True, exist_ok=True)
    shadow_log.write_text(json.dumps({
        "ts": "2026-07-01T12:00:00", "rel": "foo.py", "offset": 1, "limit": 5,
        "idx_exists": True, "idx_sections": 2, "file_lines": 10, "file_chars": 400,
    }) + "\n")
    (tmp_path / ".headroom").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".headroom" / "proxy_savings.json").write_text(json.dumps({
        "history": [
            {"timestamp": "2026-07-01T09:00:00Z", "total_tokens_saved": 100, "total_input_tokens": 1000},
            {"timestamp": "2026-07-01T12:00:00Z", "total_tokens_saved": 900, "total_input_tokens": 4000},
            {"timestamp": "2026-07-02T00:00:00Z", "total_tokens_saved": 9000, "total_input_tokens": 40000},
        ],
    }))

    # Window == single point (12:00:00): baseline = 09:00 snapshot (100/1000),
    # end = 12:00:00 snapshot (900/4000) -> delta 800/3000, not lifetime 9000.
    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()
    assert "800" in html_content
    assert "9,000" not in html_content


def test_report_builder_compression_zero_when_proxy_savings_absent(tmp_path):
    out_html = tmp_path / "combined_report.html"
    build_report(project_root=tmp_path, mode="split", output_path=out_html, store_url="sqlite:///dummy.db")
    html_content = out_html.read_text()
    assert "Compression Savings" in html_content

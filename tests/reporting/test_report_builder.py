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
from agentflow.reporting.report_builder import build_report
from agentflow.cli import cmd_report


def test_shadow_analyzer_bucketing(tmp_path):
    # Setup tasks.json with reads list
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "reads": ["file_a.py", "file_b.py#anchor"]}
        ]
    }
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks_data))

    # Setup shadow_reads.jsonl
    entries = [
        # Double count candidate
        {
            "ts": "2026-07-01T12:00:00",
            "rel": "file_b.py",
            "offset": None,
            "idx_exists": True,
            "idx_sections": 4,
            "file_lines": 100,
            "file_chars": 4000
        },
        # Standard targeted hit
        {
            "ts": "2026-07-01T12:01:00",
            "rel": "file_c.py",
            "offset": 10,
            "idx_exists": True,
            "idx_sections": 5,
            "file_lines": 200,
            "file_chars": 8000
        },
        # Gap
        {
            "ts": "2026-07-01T12:02:00",
            "rel": "file_d.py",
            "offset": None,
            "idx_exists": False,
            "idx_sections": 0,
            "file_lines": 60,
            "file_chars": 2000
        },
        # State doc
        {
            "ts": "2026-07-01T12:03:00",
            "rel": "architecture.md",
            "offset": None,
            "idx_exists": False,
            "idx_sections": 0,
            "file_lines": 500,
            "file_chars": 10000
        }
    ]

    from agentflow.shadow.analyzer import get_bucketed_stats
    
    # Reads files should be {"file_a.py", "file_b.py"}
    reads_files = {"file_a.py", "file_b.py"}
    
    # In aggregate mode:
    # file_b.py matches no-reread. Value = 4000 * 0.25 = 1000.
    stats_agg = get_bucketed_stats(tmp_path, entries, reads_files, mode="aggregate")
    assert stats_agg["no-reread"] == 1000
    assert stats_agg["targeted-reads"] == 0
    assert stats_agg["indexing-gap"] == 500
    assert stats_agg["state-docs"] == 2500

    # In split mode:
    stats_by = get_bucketed_stats(tmp_path, entries, reads_files, mode="split")
    assert stats_by["no-reread"] == 1000
    assert stats_by["targeted-reads"] == 750
    assert stats_by["indexing-gap"] == 500
    assert stats_by["state-docs"] == 2500


def test_individual_reports(tmp_path):
    # Test _report_targeted_reads
    entries_empty = []
    assert _report_targeted_reads(entries_empty) == 0

    entries = [
        {
            "rel": "file_b.py",
            "offset": None,
            "idx_exists": True,
            "idx_sections": 4,
            "file_lines": 100,
            "file_chars": 4000
        }
    ]
    assert _report_targeted_reads(entries) == 750

    # Test _report_indexing_gap
    assert _report_indexing_gap(entries_empty) == 0
    assert _report_indexing_gap(entries) == 0  # not gap because idx_exists=True
    entries_gap = [
        {
            "rel": "file_d.py",
            "offset": None,
            "idx_exists": False,
            "file_lines": 60,
            "file_chars": 2000
        }
    ]
    assert _report_indexing_gap(entries_gap) == 500

    # Test _report_lazy_decomposition
    assert _report_lazy_decomposition(tmp_path) == 0
    tasks_data = {
        "tasks": [
            {"task_id": "T-001", "status": "complete"},
            {"task_id": "T-002", "status": "pending", "reads": ["foo.py"]}
        ]
    }
    (tmp_path / "tasks.json").write_text(json.dumps(tasks_data))
    assert _report_lazy_decomposition(tmp_path) > 0

    # Test _report_no_reread
    assert _report_no_reread(entries_empty, tmp_path) == 0
    entries_vio = [
        {
            "rel": "foo.py",
            "offset": None,
            "file_chars": 1200
        }
    ]
    assert _report_no_reread(entries_vio, tmp_path) == 300

    # Test _report_state_docs
    (tmp_path / "architecture.md").write_text("Hello architecture")
    assert _report_state_docs(tmp_path) == 4

    # Test _report_verbosity_compliance
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
    # Write a dummy verbosity log
    verb_log = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    verb_log.parent.mkdir(parents=True, exist_ok=True)
    verb_log.write_text(
        json.dumps({"ts": "...", "session_type": "oracle", "turn": 1, "output_tokens": 120}) + "\n" +
        json.dumps({"ts": "...", "session_type": "oracle", "turn": 2, "output_tokens": 160}) + "\n"
    )

    # Let's mock headroom library
    mock_headroom = MagicMock()
    mock_storage = MagicMock()
    mock_storage.get_summary_stats.return_value = {"total_tokens_saved": 5000}
    mock_headroom.storage.create_storage.return_value = mock_storage
    
    # Also mock generate_report to write a file
    def mock_gen(url, path):
        Path(path).write_text("Mocked Headroom Report Content")
    mock_headroom.reporting.generator.generate_report = mock_gen

    with patch.dict(sys.modules, {"headroom": mock_headroom, "headroom.storage": mock_headroom.storage, "headroom.reporting.generator": mock_headroom.reporting.generator}):
        out_html = tmp_path / "combined_report.html"
        build_report(
            project_root=tmp_path,
            mode="aggregate",
            output_path=out_html,
            store_url="sqlite:///dummy.db"
        )
        
        assert out_html.exists()
        html_content = out_html.read_text()
        assert "aggregate" in html_content.lower()
        assert "5,000" in html_content
        assert "Mocked Headroom Report Content" in html_content
        assert "Real Tokens Used" in html_content
        assert "Shadow Mode Tokens" in html_content
        assert "Percentage Saved" in html_content

        build_report(
            project_root=tmp_path,
            mode="split",
            output_path=out_html,
            store_url="sqlite:///dummy.db"
        )
        assert out_html.exists()
        html_content_split = out_html.read_text()
        assert "Real Tokens Used" in html_content_split
        assert "Shadow Mode Tokens" in html_content_split
        assert "Percentage Saved" in html_content_split


def test_cli_report_cmd(tmp_path):
    args = argparse.Namespace(mode="aggregate", output=str(tmp_path / "cli_report.html"))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        assert cmd_report(args) == 0
        assert (tmp_path / "cli_report.html").exists()

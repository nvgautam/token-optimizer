import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from unittest.mock import patch

from agentflow.shadow.analyzer import (
    _report_targeted_reads,
    _report_indexing_gap,
    _report_lazy_decomposition,
    _report_no_reread,
    _report_state_docs,
    _report_verbosity_compliance,
    main as analyzer_main
)

@pytest.fixture
def utc_tz(monkeypatch):
    # Pin local tz to UTC so window/history comparisons are deterministic.
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()

def test_shadow_analyzer_bucketing(tmp_path):
    tasks_data = {"tasks": [{"task_id": "T-001", "reads": ["file_a.py", "file_b.py#anchor"]}]}
    (tmp_path / "tasks.json").write_text(json.dumps(tasks_data))

    entries = [
        {"ts": "2026-07-01T12:00:00", "rel": "file_b.py", "offset": None, "idx_exists": True, "idx_sections": 4, "file_lines": 100, "file_chars": 4000},  # double-count candidate
        {"ts": "2026-07-01T12:01:00", "rel": "file_c.py", "offset": 10, "idx_exists": True, "idx_sections": 5, "file_lines": 200, "file_chars": 8000},  # targeted hit
        {"ts": "2026-07-01T12:02:00", "rel": "file_d.py", "offset": None, "idx_exists": False, "idx_sections": 0, "file_lines": 60, "file_chars": 2000},  # gap
        {"ts": "2026-07-01T12:03:00", "rel": "architecture.md", "offset": None, "idx_exists": False, "idx_sections": 0, "file_lines": 500, "file_chars": 10000},  # state doc
    ]

    from agentflow.shadow.analyzer import get_bucketed_stats

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

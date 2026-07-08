import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json

from agentflow.shadow.verbosity_ab import (
    FALLBACK_BASELINE_TOKENS,
    record_turn,
    import_from_verbosity_log,
    load_arm_entries,
    compute_arm_stats,
    run_ab_comparison,
    load_baseline,
    run_verbosity_ab,
)


def test_record_turn_appends_tagged_entry(tmp_path):
    record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=123, arm="off")
    log_path = tmp_path / ".agentflow" / "verbosity_ab_log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().splitlines()[0])
    assert entry["session_type"] == "oracle"
    assert entry["turn"] == 1
    assert entry["output_tokens"] == 123
    assert entry["arm"] == "off"
    assert "ts" in entry


def test_record_turn_rejects_unknown_arm(tmp_path):
    try:
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=100, arm="bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_import_from_verbosity_log_no_source_file(tmp_path):
    assert import_from_verbosity_log(tmp_path) == 0


def test_import_from_verbosity_log_tags_entries(tmp_path):
    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200, "arm": "on"}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:01:00", "session_type": "worker", "turn": 2, "output_tokens": 300, "arm": "on"}) + "\n"
    )
    count = import_from_verbosity_log(tmp_path)
    assert count == 2
    entries = load_arm_entries(tmp_path, "on")
    assert len(entries) == 2
    assert all(e["arm"] == "on" for e in entries)
    assert {e["output_tokens"] for e in entries} == {200, 300}


def test_import_from_verbosity_log_since_ts_filters(tmp_path):
    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200, "arm": "off"}) + "\n" +
        json.dumps({"ts": "2026-07-01T11:00:00", "session_type": "worker", "turn": 2, "output_tokens": 300, "arm": "off"}) + "\n"
    )
    count = import_from_verbosity_log(tmp_path, since_ts="2026-07-01T10:30:00")
    assert count == 1
    entries = load_arm_entries(tmp_path, "off")
    assert entries[0]["output_tokens"] == 300


def test_import_from_verbosity_log_rerun_without_since_ts_is_idempotent(tmp_path):
    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200, "arm": "on"}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:01:00", "session_type": "worker", "turn": 2, "output_tokens": 300, "arm": "on"}) + "\n"
    )
    first = import_from_verbosity_log(tmp_path)
    second = import_from_verbosity_log(tmp_path)
    assert first == 2
    assert second == 0
    assert len(load_arm_entries(tmp_path, "on")) == 2


def test_load_arm_entries_filters_by_arm(tmp_path):
    record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=100, arm="on")
    record_turn(tmp_path, session_type="oracle", turn=2, output_tokens=200, arm="off")
    assert len(load_arm_entries(tmp_path, "on")) == 1
    assert len(load_arm_entries(tmp_path, "off")) == 1
    assert load_arm_entries(tmp_path, "on")[0]["output_tokens"] == 100


def test_load_arm_entries_empty_when_no_log(tmp_path):
    assert load_arm_entries(tmp_path, "on") == []


def test_compute_arm_stats_empty():
    stats = compute_arm_stats([])
    assert stats["n"] == 0
    assert stats["mean"] == 0.0
    assert stats["ci95_low"] is None
    assert stats["ci95_high"] is None


def test_compute_arm_stats_single_sample_no_ci():
    stats = compute_arm_stats([500])
    assert stats["n"] == 1
    assert stats["mean"] == 500
    assert stats["ci95_low"] is None
    assert stats["ci95_high"] is None


def test_compute_arm_stats_multi_sample():
    tokens = [100, 200, 300, 400, 500]
    stats = compute_arm_stats(tokens)
    assert stats["n"] == 5
    assert stats["mean"] == 300
    assert stats["p90"] == 500
    assert stats["ci95_low"] is not None
    assert stats["ci95_high"] is not None
    assert stats["ci95_low"] < stats["mean"] < stats["ci95_high"]


def test_run_ab_comparison_no_data_uses_fallback(tmp_path):
    result = run_ab_comparison(tmp_path)
    assert result["measured"] is False
    assert result["baseline_tokens"] == FALLBACK_BASELINE_TOKENS
    assert result["sample_size"] == 0
    baseline_path = tmp_path / ".agentflow" / "verbosity_baseline.json"
    assert baseline_path.exists()


def test_run_ab_comparison_with_data(tmp_path):
    for tok in (400, 500, 600):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="off")
    for tok in (100, 150, 200):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="on")

    result = run_ab_comparison(tmp_path)
    assert result["measured"] is True
    assert result["baseline_tokens"] == 500
    assert result["sample_size"] == 3
    assert result["arms"]["on"]["mean"] == 150
    assert result["arms"]["off"]["mean"] == 500


def test_load_baseline_returns_fallback_when_missing(tmp_path):
    baseline = load_baseline(tmp_path)
    assert baseline["measured"] is False
    assert baseline["baseline_tokens"] == FALLBACK_BASELINE_TOKENS
    assert baseline["sample_size"] == 0


def test_load_baseline_returns_persisted_result(tmp_path):
    record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=450, arm="off")
    run_ab_comparison(tmp_path)
    baseline = load_baseline(tmp_path)
    assert baseline["measured"] is True
    assert baseline["baseline_tokens"] == 450


def test_load_baseline_handles_corrupt_file(tmp_path):
    baseline_path = tmp_path / ".agentflow" / "verbosity_baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("not-json")
    baseline = load_baseline(tmp_path)
    assert baseline["measured"] is False
    assert baseline["baseline_tokens"] == FALLBACK_BASELINE_TOKENS


def test_run_verbosity_ab_returns_comparison_result(tmp_path, capsys):
    for tok in (300, 400):
        record_turn(tmp_path, session_type="worker", turn=1, output_tokens=tok, arm="off")
    result = run_verbosity_ab(tmp_path)
    assert result["measured"] is True
    assert result["baseline_tokens"] == 350
    captured = capsys.readouterr()
    assert "A/B" in captured.out


def test_run_verbosity_ab_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_verbosity_ab()
    assert result["measured"] is False


def test_run_ab_comparison_session_type_none_returns_all(tmp_path):
    """session_type=None includes entries from all session types."""
    for tok in (400, 500):
        record_turn(tmp_path, session_type="orchestrator", turn=1, output_tokens=tok, arm="off")
    for tok in (300, 350):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="off")

    result = run_ab_comparison(tmp_path, session_type=None)
    assert result["arms"]["off"]["n"] == 4


def test_run_ab_comparison_filters_by_session_type(tmp_path):
    """session_type='orchestrator' includes only orchestrator entries."""
    for tok in (400, 500, 600):
        record_turn(tmp_path, session_type="orchestrator", turn=1, output_tokens=tok, arm="off")
    for tok in (100, 200):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="off")

    result = run_ab_comparison(tmp_path, session_type="orchestrator")
    assert result["arms"]["off"]["n"] == 3
    assert result["arms"]["off"]["mean"] == 500.0


def test_run_ab_comparison_session_type_mismatch_returns_empty(tmp_path):
    """session_type that matches no entries returns unmeasured fallback."""
    for tok in (400, 500):
        record_turn(tmp_path, session_type="orchestrator", turn=1, output_tokens=tok, arm="off")

    result = run_ab_comparison(tmp_path, session_type="worker")
    assert result["arms"]["off"]["n"] == 0
    assert result["measured"] is False
    assert (tmp_path / ".agentflow" / "verbosity_baseline.json").exists()


def test_session_manager_reads_arm_from_file_present(tmp_path):
    from agentflow.shell.session_manager import SessionManager
    from unittest.mock import patch, MagicMock

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(exist_ok=True)
    arm_file = agentflow_dir / "verbosity_ab_arm.txt"
    arm_file.write_text("on\n", encoding="utf-8")

    pty = MagicMock()
    tok = MagicMock()
    tok.count_tokens.return_value = 5
    tok.accumulate.return_value = 5

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        sm = SessionManager(pty, tok, {})
        assert sm._arm == "on"


def test_session_manager_reads_arm_from_file_absent(tmp_path):
    from agentflow.shell.session_manager import SessionManager
    from unittest.mock import patch, MagicMock

    pty = MagicMock()
    tok = MagicMock()

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        sm = SessionManager(pty, tok, {})
        assert sm._arm is None


def test_session_manager_writes_entries_with_arm(tmp_path):
    from agentflow.shell.session_manager import SessionManager
    from unittest.mock import patch, MagicMock

    agentflow_dir = tmp_path / ".agentflow"
    agentflow_dir.mkdir(exist_ok=True)
    arm_file = agentflow_dir / "verbosity_ab_arm.txt"
    arm_file.write_text("off\n", encoding="utf-8")

    pty = MagicMock()
    tok = MagicMock()
    tok.count_tokens.return_value = 10
    tok.accumulate.return_value = 10

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        sm = SessionManager(pty, tok, {})
        sm.session_type = "oracle"
        
        # Invoke callback registered on pty — AGENTFLOW_TASK_COMPLETE is the turn boundary
        sm._task_start_tokens = {"T-001": 0}
        sm._handle_output(b"AGENTFLOW_TASK_COMPLETE:T-001\n")

    log_path = agentflow_dir / "verbosity_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["arm"] == "off"


def test_import_from_verbosity_log_uses_entry_arm_and_warns(tmp_path):
    import warnings
    from agentflow.shadow.verbosity_ab import import_from_verbosity_log, load_arm_entries

    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200, "arm": "on"}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:01:00", "session_type": "worker", "turn": 2, "output_tokens": 300, "arm": "off"}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:02:00", "session_type": "worker", "turn": 3, "output_tokens": 400}) + "\n"
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        count = import_from_verbosity_log(tmp_path, arm="on")
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated" in str(w[0].message)

    assert count == 2

    hook_on_entries = load_arm_entries(tmp_path, "on")
    hook_off_entries = load_arm_entries(tmp_path, "off")
    assert len(hook_on_entries) == 1
    assert hook_on_entries[0]["output_tokens"] == 200
    assert len(hook_off_entries) == 1
    assert hook_off_entries[0]["output_tokens"] == 300


def test_import_from_verbosity_log_no_arm_passed(tmp_path):
    from agentflow.shadow.verbosity_ab import import_from_verbosity_log, load_arm_entries

    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200, "arm": "on"}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:01:00", "session_type": "worker", "turn": 2, "output_tokens": 300, "arm": "off"}) + "\n"
    )

    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        count = import_from_verbosity_log(tmp_path)
        assert len(w) == 0

    assert count == 2
    assert len(load_arm_entries(tmp_path, "on")) == 1
    assert len(load_arm_entries(tmp_path, "off")) == 1

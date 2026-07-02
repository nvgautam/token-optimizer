import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import json

from agentflow.shadow.verbosity_ab import (
    ARMS,
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
    record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=123, arm="hook_off")
    log_path = tmp_path / ".agentflow" / "verbosity_ab_log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().splitlines()[0])
    assert entry["session_type"] == "oracle"
    assert entry["turn"] == 1
    assert entry["output_tokens"] == 123
    assert entry["arm"] == "hook_off"
    assert "ts" in entry


def test_record_turn_rejects_unknown_arm(tmp_path):
    try:
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=100, arm="bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_import_from_verbosity_log_no_source_file(tmp_path):
    assert import_from_verbosity_log(tmp_path, arm="hook_on") == 0


def test_import_from_verbosity_log_tags_entries(tmp_path):
    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:01:00", "session_type": "worker", "turn": 2, "output_tokens": 300}) + "\n"
    )
    count = import_from_verbosity_log(tmp_path, arm="hook_on")
    assert count == 2
    entries = load_arm_entries(tmp_path, "hook_on")
    assert len(entries) == 2
    assert all(e["arm"] == "hook_on" for e in entries)
    assert {e["output_tokens"] for e in entries} == {200, 300}


def test_import_from_verbosity_log_since_ts_filters(tmp_path):
    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200}) + "\n" +
        json.dumps({"ts": "2026-07-01T11:00:00", "session_type": "worker", "turn": 2, "output_tokens": 300}) + "\n"
    )
    count = import_from_verbosity_log(tmp_path, arm="hook_off", since_ts="2026-07-01T10:30:00")
    assert count == 1
    entries = load_arm_entries(tmp_path, "hook_off")
    assert entries[0]["output_tokens"] == 300


def test_import_from_verbosity_log_rerun_without_since_ts_is_idempotent(tmp_path):
    src = tmp_path / ".agentflow" / "verbosity_log.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00", "session_type": "worker", "turn": 1, "output_tokens": 200}) + "\n" +
        json.dumps({"ts": "2026-07-01T10:01:00", "session_type": "worker", "turn": 2, "output_tokens": 300}) + "\n"
    )
    first = import_from_verbosity_log(tmp_path, arm="hook_on")
    second = import_from_verbosity_log(tmp_path, arm="hook_on")
    assert first == 2
    assert second == 0
    assert len(load_arm_entries(tmp_path, "hook_on")) == 2


def test_load_arm_entries_filters_by_arm(tmp_path):
    record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=100, arm="hook_on")
    record_turn(tmp_path, session_type="oracle", turn=2, output_tokens=200, arm="hook_off")
    assert len(load_arm_entries(tmp_path, "hook_on")) == 1
    assert len(load_arm_entries(tmp_path, "hook_off")) == 1
    assert load_arm_entries(tmp_path, "hook_on")[0]["output_tokens"] == 100


def test_load_arm_entries_empty_when_no_log(tmp_path):
    assert load_arm_entries(tmp_path, "hook_on") == []


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
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="hook_off")
    for tok in (100, 150, 200):
        record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=tok, arm="hook_on")

    result = run_ab_comparison(tmp_path)
    assert result["measured"] is True
    assert result["baseline_tokens"] == 500
    assert result["sample_size"] == 3
    assert result["arms"]["hook_on"]["mean"] == 150
    assert result["arms"]["hook_off"]["mean"] == 500


def test_load_baseline_returns_fallback_when_missing(tmp_path):
    baseline = load_baseline(tmp_path)
    assert baseline["measured"] is False
    assert baseline["baseline_tokens"] == FALLBACK_BASELINE_TOKENS
    assert baseline["sample_size"] == 0


def test_load_baseline_returns_persisted_result(tmp_path):
    record_turn(tmp_path, session_type="oracle", turn=1, output_tokens=450, arm="hook_off")
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
        record_turn(tmp_path, session_type="worker", turn=1, output_tokens=tok, arm="hook_off")
    result = run_verbosity_ab(tmp_path)
    assert result["measured"] is True
    assert result["baseline_tokens"] == 350
    captured = capsys.readouterr()
    assert "A/B" in captured.out


def test_run_verbosity_ab_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_verbosity_ab()
    assert result["measured"] is False
    assert (tmp_path / ".agentflow" / "verbosity_baseline.json").exists()

import sys
import json
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from agentflow.shadow.worker_token_spike import compute_worker_mean_tokens


@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_compute_worker_mean_tokens_basic(mock_home):
    """Test basic computation with 2 tasks (4 entries each)."""
    log_file = mock_home / "task_token_log.jsonl"
    calib_file = mock_home / "rate_calibration_claude.json"

    # Task A: 4 entries summing to 1000 tokens
    # Task B: 4 entries summing to 2000 tokens
    # Expected mean = (1000 + 2000) / 2 = 1500.0
    entries = [
        {"task_id": "T-001", "session_type": "worker", "token_delta": 250, "timestamp": "2026-07-01T21:00:00"},
        {"task_id": "T-001", "session_type": "worker", "token_delta": 250, "timestamp": "2026-07-01T21:01:00"},
        {"task_id": "T-001", "session_type": "worker", "token_delta": 250, "timestamp": "2026-07-01T21:02:00"},
        {"task_id": "T-001", "session_type": "worker", "token_delta": 250, "timestamp": "2026-07-01T21:03:00"},
        {"task_id": "T-002", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:10:00"},
        {"task_id": "T-002", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:11:00"},
        {"task_id": "T-002", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:12:00"},
        {"task_id": "T-002", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:13:00"},
    ]

    with open(log_file, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    result = compute_worker_mean_tokens(str(log_file), str(calib_file))

    assert result["worker_mean_tokens"] == 1500.0
    assert result["sample_count"] == 2
    assert set(result["task_ids"]) == {"T-001", "T-002"}


def test_compute_worker_mean_tokens_filters_sparse_tasks(mock_home):
    """Test that tasks with < 3 entries are excluded."""
    log_file = mock_home / "task_token_log.jsonl"
    calib_file = mock_home / "rate_calibration_claude.json"

    # Task A: 5 entries summing to 1000 tokens (included)
    # Task B: 2 entries summing to 500 tokens (excluded, < 3 entries)
    # Expected mean = 1000.0 / 1 = 1000.0
    entries = [
        {"task_id": "T-A", "session_type": "worker", "token_delta": 200, "timestamp": "2026-07-01T21:00:00"},
        {"task_id": "T-A", "session_type": "worker", "token_delta": 200, "timestamp": "2026-07-01T21:01:00"},
        {"task_id": "T-A", "session_type": "worker", "token_delta": 200, "timestamp": "2026-07-01T21:02:00"},
        {"task_id": "T-A", "session_type": "worker", "token_delta": 200, "timestamp": "2026-07-01T21:03:00"},
        {"task_id": "T-A", "session_type": "worker", "token_delta": 200, "timestamp": "2026-07-01T21:04:00"},
        {"task_id": "T-B", "session_type": "worker", "token_delta": 250, "timestamp": "2026-07-01T21:10:00"},
        {"task_id": "T-B", "session_type": "worker", "token_delta": 250, "timestamp": "2026-07-01T21:11:00"},
    ]

    with open(log_file, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    result = compute_worker_mean_tokens(str(log_file), str(calib_file))

    assert result["worker_mean_tokens"] == 1000.0
    assert result["sample_count"] == 1
    assert result["task_ids"] == ["T-A"]


def test_compute_worker_mean_tokens_empty_log(mock_home):
    """Test with empty JSONL file."""
    log_file = mock_home / "task_token_log.jsonl"
    calib_file = mock_home / "rate_calibration_claude.json"

    # Create empty file
    log_file.write_text("")

    result = compute_worker_mean_tokens(str(log_file), str(calib_file))

    assert result["worker_mean_tokens"] == 0.0
    assert result["sample_count"] == 0
    assert result["task_ids"] == []


def test_compute_worker_mean_tokens_missing_log(mock_home):
    """Test with non-existent log file."""
    log_file = mock_home / "nonexistent_log.jsonl"
    calib_file = mock_home / "rate_calibration_claude.json"

    # Don't create the file
    result = compute_worker_mean_tokens(str(log_file), str(calib_file))

    assert result["worker_mean_tokens"] == 0.0
    assert result["sample_count"] == 0
    assert result["task_ids"] == []


def test_update_calibration_adds_field(mock_home):
    """Test that --update flag writes worker_mean_tokens to calibration file."""
    log_file = mock_home / "task_token_log.jsonl"
    calib_file = mock_home / "rate_calibration_claude.json"

    # Create log with 2 tasks (each totaling to 1500 tokens)
    entries = [
        {"task_id": "T-100", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:00:00"},
        {"task_id": "T-100", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:01:00"},
        {"task_id": "T-100", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:02:00"},
        {"task_id": "T-200", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:10:00"},
        {"task_id": "T-200", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:11:00"},
        {"task_id": "T-200", "session_type": "worker", "token_delta": 500, "timestamp": "2026-07-01T21:12:00"},
    ]

    with open(log_file, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    # Pre-populate calibration file with existing keys
    existing_cal = {
        "timestamp": "2026-07-01T20:00:00",
        "ewma_mean_tokens": 2000.0,
        "sample_count": 5,
    }
    with open(calib_file, "w") as f:
        json.dump(existing_cal, f)

    # Import and use the update function
    from agentflow.shadow.worker_token_spike import update_calibration_file

    update_calibration_file(str(log_file), str(calib_file))

    # Verify the file was updated
    with open(calib_file, "r") as f:
        updated_cal = json.load(f)

    # Should have all existing keys plus the new worker_mean_tokens
    assert "worker_mean_tokens" in updated_cal
    assert abs(updated_cal["worker_mean_tokens"] - 1500.0) < 1e-5
    assert updated_cal["timestamp"] == "2026-07-01T20:00:00"  # Preserved
    assert updated_cal["ewma_mean_tokens"] == 2000.0  # Preserved
    assert updated_cal["sample_count"] == 5  # Preserved

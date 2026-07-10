"""Tests for agentflow.shadow.task_estimator."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from agentflow.shadow.task_estimator import (
    aggregate_tokens,
    compute,
    compute_stats,
    estimate,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_aggregate_tokens_sums_by_task_id():
    records = [
        {"task_id": "T-001", "token_delta": 100},
        {"task_id": "T-001", "token_delta": -50},  # abs → 50
        {"task_id": "T-002", "token_delta": 200},
        {"task_id": "T-002", "token_delta": 300},
        {"task_id": "T-003", "token_delta": 75},
    ]
    result = aggregate_tokens(records)
    assert result == {"T-001": 150, "T-002": 500, "T-003": 75}


def test_estimate_returns_static_default_when_few_samples(tmp_path):
    log = tmp_path / "task_token_log.jsonl"
    out = tmp_path / "task_estimator.json"
    # Only 3 tasks (< 7 minimum samples)
    records = [
        {"task_id": "T-001", "token_delta": 1000},
        {"task_id": "T-002", "token_delta": 2000},
        {"task_id": "T-003", "token_delta": 3000},
    ]
    _write_jsonl(log, records)
    compute(log_path=log, output_path=out)
    result = estimate(estimated_lines=100, file_count=5, stats_path=out)
    assert result == 2500


def test_estimate_returns_mean_when_low_cv(tmp_path):
    log = tmp_path / "task_token_log.jsonl"
    out = tmp_path / "task_estimator.json"
    # 10 tasks with tightly clustered values → cv < 0.5
    values = [950, 1000, 1050, 980, 1020, 990, 1010, 970, 1030, 1000]
    records = [{"task_id": f"T-{i:03d}", "token_delta": v} for i, v in enumerate(values)]
    _write_jsonl(log, records)
    stats = compute(log_path=log, output_path=out)
    assert stats["cv"] < 0.5, f"Expected low cv, got {stats['cv']}"
    result = estimate(estimated_lines=100, file_count=5, stats_path=out)
    assert result == int(stats["mean"])


def test_estimate_returns_p85_when_high_cv(tmp_path):
    log = tmp_path / "task_token_log.jsonl"
    out = tmp_path / "task_estimator.json"
    # 10 tasks with wildly different values → cv >= 0.5
    values = [100, 5000, 200, 8000, 150, 7000, 300, 6000, 250, 4000]
    records = [{"task_id": f"T-{i:03d}", "token_delta": v} for i, v in enumerate(values)]
    _write_jsonl(log, records)
    stats = compute(log_path=log, output_path=out)
    assert stats["cv"] >= 0.5, f"Expected high cv, got {stats['cv']}"
    result = estimate(estimated_lines=100, file_count=5, stats_path=out)
    assert result == int(stats["p85"])


def test_writes_task_estimator_json(tmp_path):
    log = tmp_path / "task_token_log.jsonl"
    out = tmp_path / "task_estimator.json"
    records = [{"task_id": f"T-{i:03d}", "token_delta": 1000 + i * 100} for i in range(5)]
    _write_jsonl(log, records)
    compute(log_path=log, output_path=out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    for key in ("mean", "p85", "cv", "sample_count", "timestamp"):
        assert key in data, f"Missing key: {key}"
    assert data["sample_count"] == 5


def test_p85_computation(tmp_path):
    log = tmp_path / "task_token_log.jsonl"
    out = tmp_path / "task_estimator.json"
    # 10 tasks with values 100, 200, ..., 1000 (one record per task)
    values = [i * 100 for i in range(1, 11)]
    records = [{"task_id": f"T-{i:03d}", "token_delta": v} for i, v in enumerate(values)]
    _write_jsonl(log, records)
    stats = compute(log_path=log, output_path=out)
    # Linear interpolation: idx = 0.85 * (10-1) = 7.65
    # sorted[7]=800, sorted[8]=900 → 800 + 0.65 * 100 = 865.0
    assert abs(stats["p85"] - 865.0) < 0.01


def test_cv_computation(tmp_path):
    log = tmp_path / "task_token_log.jsonl"
    out = tmp_path / "task_estimator.json"
    values = [1000, 2000, 3000]
    records = [{"task_id": f"T-{i:03d}", "token_delta": v} for i, v in enumerate(values)]
    _write_jsonl(log, records)
    stats = compute(log_path=log, output_path=out)
    expected_cv = statistics.stdev(values) / statistics.mean(values)
    assert abs(stats["cv"] - expected_cv) < 1e-9

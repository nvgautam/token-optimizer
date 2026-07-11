"""Tests for agentflow.shadow.model_ab — Haiku vs Sonnet A/B analysis."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentflow.shadow.model_ab import load_model_baseline, run_model_ab


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_proxy_log(tmp_path: Path, entries: list[dict]) -> None:
    log_dir = tmp_path / ".agentflow"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "proxy_log.jsonl"
    with open(log_file, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _haiku_entry(output_tokens: int) -> dict:
    return {"model": "claude-haiku-4-5-20251001", "output_tokens": output_tokens}


def _sonnet_entry(output_tokens: int) -> dict:
    return {"model": "claude-sonnet-4-6", "output_tokens": output_tokens}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_model_ab_empty_log(tmp_path: Path) -> None:
    """No proxy_log.jsonl → measured=False, n=0 for both arms."""
    result = run_model_ab(tmp_path)
    assert result["measured"] is False
    assert result["models"]["haiku"]["n"] == 0
    assert result["models"]["sonnet"]["n"] == 0


def test_run_model_ab_no_model_field(tmp_path: Path) -> None:
    """Entries without model field are skipped → unmeasured fallback."""
    _write_proxy_log(tmp_path, [
        {"output_tokens": 100},
        {"output_tokens": 200},
    ])
    result = run_model_ab(tmp_path)
    assert result["measured"] is False
    assert result["models"]["haiku"]["n"] == 0
    assert result["models"]["sonnet"]["n"] == 0


def test_run_model_ab_haiku_only(tmp_path: Path) -> None:
    """Only haiku entries → haiku n≥1, sonnet n=0 → measured=False."""
    _write_proxy_log(tmp_path, [_haiku_entry(200) for _ in range(5)])
    result = run_model_ab(tmp_path)
    assert result["measured"] is False
    assert result["models"]["haiku"]["n"] == 5
    assert result["models"]["sonnet"]["n"] == 0


def test_run_model_ab_both_arms(tmp_path: Path) -> None:
    """10 haiku (200 tokens) + 10 sonnet (300 tokens) → measured=True, correct stats."""
    entries = [_haiku_entry(200) for _ in range(10)] + [_sonnet_entry(300) for _ in range(10)]
    _write_proxy_log(tmp_path, entries)
    result = run_model_ab(tmp_path)
    assert result["measured"] is True
    assert result["models"]["haiku"]["n"] == 10
    assert result["models"]["haiku"]["mean"] == pytest.approx(200.0)
    assert result["models"]["sonnet"]["n"] == 10
    assert result["models"]["sonnet"]["mean"] == pytest.approx(300.0)
    # delta_pct = (300 - 200) / 200 * 100 = 50%
    assert result["delta_pct"] == pytest.approx(50.0, abs=0.5)


def test_run_model_ab_persists_baseline(tmp_path: Path) -> None:
    """After run_model_ab, .agentflow/model_ab_baseline.json must exist."""
    entries = [_haiku_entry(200) for _ in range(10)] + [_sonnet_entry(300) for _ in range(10)]
    _write_proxy_log(tmp_path, entries)
    run_model_ab(tmp_path)
    baseline_file = tmp_path / ".agentflow" / "model_ab_baseline.json"
    assert baseline_file.exists()
    data = json.loads(baseline_file.read_text())
    assert "models" in data
    assert "measured" in data


def test_load_model_baseline_absent(tmp_path: Path) -> None:
    """No baseline file → unmeasured fallback returned, no exception raised."""
    result = load_model_baseline(tmp_path)
    assert result["measured"] is False
    assert "models" in result


def test_load_model_baseline_reads_file(tmp_path: Path) -> None:
    """When baseline file exists, load_model_baseline returns its content."""
    baseline_dir = tmp_path / ".agentflow"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    payload = {"measured": True, "models": {"haiku": {"n": 10, "mean": 150.0, "p90": 200.0},
                                             "sonnet": {"n": 10, "mean": 250.0, "p90": 300.0}},
               "delta_pct": 66.7}
    (baseline_dir / "model_ab_baseline.json").write_text(json.dumps(payload))
    result = load_model_baseline(tmp_path)
    assert result["measured"] is True
    assert result["models"]["haiku"]["mean"] == pytest.approx(150.0)
    assert result["delta_pct"] == pytest.approx(66.7)


def test_delta_pct_zero_when_insufficient(tmp_path: Path) -> None:
    """n < 5 for either arm → delta_pct=0.0."""
    # 3 haiku entries, 3 sonnet entries — both below MIN_SAMPLES=5
    entries = [_haiku_entry(200) for _ in range(3)] + [_sonnet_entry(300) for _ in range(3)]
    _write_proxy_log(tmp_path, entries)
    result = run_model_ab(tmp_path)
    assert result["measured"] is False
    assert result["delta_pct"] == pytest.approx(0.0)

"""Tests for T-096: code_size_savings and code_size_bootstrap modules."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

import pytest

from agentflow.reporting.code_size_savings import (
    load_file_families,
    compute_code_size_savings,
    daily_code_size_savings,
)


# --------------------------------------------------------------------------- #
# load_file_families tests (scenarios 1-2)
# --------------------------------------------------------------------------- #


def test_load_file_families_empty(tmp_path):
    """Missing file returns empty dict."""
    result = load_file_families(tmp_path / "nonexistent.jsonl")
    assert result == {}


def test_load_file_families_empty_file(tmp_path):
    """Empty file returns empty dict."""
    f = tmp_path / "file_families.jsonl"
    f.write_text("")
    assert load_file_families(f) == {}


def test_load_file_families_with_entries(tmp_path):
    """Parses jsonl correctly."""
    f = tmp_path / "file_families.jsonl"
    f.write_text(
        json.dumps({"parent": "big.py", "children": ["part_a.py", "part_b.py"], "ts": "2026-06-01"}) + "\n"
        + json.dumps({"parent": "other.py", "children": ["other_a.py"], "ts": "2026-06-02"}) + "\n"
    )
    result = load_file_families(f)
    assert result == {
        "big.py": ["part_a.py", "part_b.py"],
        "other.py": ["other_a.py"],
    }


def test_load_file_families_skips_bad_lines(tmp_path):
    """Bad JSON lines are skipped."""
    f = tmp_path / "file_families.jsonl"
    f.write_text(
        "not-json\n"
        + json.dumps({"parent": "good.py", "children": ["good_a.py"]}) + "\n"
    )
    result = load_file_families(f)
    assert result == {"good.py": ["good_a.py"]}


# --------------------------------------------------------------------------- #
# compute_code_size_savings tests (scenarios 3-4)
# --------------------------------------------------------------------------- #


def test_compute_code_size_savings_no_match():
    """Entries with no family match → 0 savings."""
    shadow_entries = [
        {"rel": "unrelated.py", "file_lines": 100, "ts": "2026-07-01T12:00:00"},
        {"rel": "also_unrelated.py", "file_lines": 200, "ts": "2026-07-01T12:01:00"},
    ]
    families = {"big.py": ["part_a.py", "part_b.py"]}
    result = compute_code_size_savings(shadow_entries, families)
    assert result["total_saved_tokens"] == 0
    assert result["families_count"] == 1
    assert result["reads_count"] == 0


def test_compute_code_size_savings_empty_families():
    """No families → 0 savings."""
    shadow_entries = [{"rel": "foo.py", "file_lines": 100, "ts": "2026-07-01T12:00:00"}]
    result = compute_code_size_savings(shadow_entries, {})
    assert result["total_saved_tokens"] == 0
    assert result["families_count"] == 0


def test_compute_code_size_savings_with_family():
    """Child file entry, shadow_size > file_lines → positive savings."""
    # Family: big.py → [part_a.py, part_b.py]
    # part_a: 100 lines, part_b: 120 lines
    # shadow_size = 0 (parent) + 100 + 120 = 220
    # reading part_a: savings = 220 - 100 = 120 lines → 480 tokens
    # reading part_b: savings = 220 - 120 = 100 lines → 400 tokens
    # total: 880 tokens
    families = {"big.py": ["part_a.py", "part_b.py"]}
    shadow_entries = [
        {"rel": "part_a.py", "file_lines": 100, "ts": "2026-07-01T12:00:00"},
        {"rel": "part_b.py", "file_lines": 120, "ts": "2026-07-01T12:01:00"},
    ]
    result = compute_code_size_savings(shadow_entries, families)
    assert result["total_saved_tokens"] > 0
    assert result["families_count"] == 1
    assert result["reads_count"] == 2
    assert result["total_saved_tokens"] == 880


def test_compute_code_size_savings_token_multiplier():
    """1 line saved = 4 tokens (consistent with rest of codebase)."""
    families = {"parent.py": ["child_a.py", "child_b.py", "child_c.py"]}
    shadow_entries = [
        {"rel": "child_a.py", "file_lines": 50, "ts": "2026-07-01T12:00:00"},
        {"rel": "child_b.py", "file_lines": 50, "ts": "2026-07-01T12:00:00"},
        {"rel": "child_c.py", "file_lines": 50, "ts": "2026-07-01T12:00:00"},
    ]
    result = compute_code_size_savings(shadow_entries, families)
    # shadow_size = 0 + 50 + 50 + 50 = 150
    # each read: 150 - 50 = 100 lines → 400 tokens
    # total: 3 × 400 = 1200 tokens
    assert result["total_saved_tokens"] == 1200


# --------------------------------------------------------------------------- #
# daily_code_size_savings tests (scenario 5)
# --------------------------------------------------------------------------- #


def test_daily_code_size_savings_groups_by_date():
    """Entries on same date aggregate."""
    families = {"big.py": ["part_a.py", "part_b.py"]}
    shadow_entries = [
        {"rel": "part_a.py", "file_lines": 100, "ts": "2026-07-01T10:00:00"},
        {"rel": "part_b.py", "file_lines": 100, "ts": "2026-07-01T14:00:00"},
        {"rel": "part_a.py", "file_lines": 100, "ts": "2026-07-02T10:00:00"},
    ]
    result = daily_code_size_savings(shadow_entries, families, days=14)
    assert len(result) == 2
    dates = {r["date"] for r in result}
    assert "2026-07-01" in dates
    assert "2026-07-02" in dates
    jul1 = next(r for r in result if r["date"] == "2026-07-01")
    jul2 = next(r for r in result if r["date"] == "2026-07-02")
    assert jul1["code_size"] > 0
    assert jul2["code_size"] > 0
    assert jul1["code_size"] == jul2["code_size"] * 2


def test_daily_code_size_savings_no_family_match():
    """No family match → empty result."""
    result = daily_code_size_savings(
        [{"rel": "unrelated.py", "file_lines": 100, "ts": "2026-07-01T00:00:00"}],
        {"big.py": ["part_a.py"]},
        days=14,
    )
    assert result == []


def test_daily_code_size_savings_respects_days_limit():
    """Returns at most `days` entries."""
    families = {"big.py": ["child.py", "child2.py"]}
    shadow_entries = [
        {"rel": "child.py", "file_lines": 50, "ts": f"2026-06-{i:02d}T00:00:00"}
        for i in range(1, 21)
    ]
    result = daily_code_size_savings(shadow_entries, families, days=7)
    assert len(result) <= 7


# --------------------------------------------------------------------------- #
# bootstrap tests (scenario 6)
# --------------------------------------------------------------------------- #


def test_bootstrap_detects_split_event(tmp_path):
    """Mock git log with a shrink commit + new siblings → family written."""
    from agentflow.reporting import code_size_bootstrap

    sha = "abc123def456"
    parent_sha = "parent000sha"

    def mock_run(cmd, cwd=None, capture_output=False, text=False):
        m = MagicMock()
        m.returncode = 0
        cmd_str = " ".join(cmd)
        if "log" in cmd_str and "--format=%H %aI" in cmd_str:
            m.stdout = f"{sha} 2026-06-01T12:00:00+00:00\n"
        elif "diff-tree" in cmd_str and sha in cmd_str:
            m.stdout = "M\tagentflow.py\nA\tagentflow/module_a.py\nA\tagentflow/module_b.py\n"
        elif "rev-parse" in cmd_str and f"{sha}^" in cmd_str:
            m.stdout = f"{parent_sha}\n"
        elif "show" in cmd_str and f"{parent_sha}:agentflow.py" in cmd_str:
            m.stdout = "line\n" * 300  # 300 lines before
        elif "show" in cmd_str and f"{sha}:agentflow.py" in cmd_str:
            m.stdout = "line\n" * 100  # 100 lines after (shrank 67%)
        else:
            m.stdout = ""
        return m

    with patch("agentflow.reporting.code_size_bootstrap.subprocess.run", side_effect=mock_run):
        families_path = tmp_path / ".agentflow" / "file_families.jsonl"
        code_size_bootstrap.bootstrap(cwd=tmp_path, families_path=families_path)

    assert families_path.exists()
    lines = [json.loads(ln) for ln in families_path.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1
    assert lines[0]["parent"] == "agentflow.py"
    assert "agentflow/module_a.py" in lines[0]["children"]
    assert "agentflow/module_b.py" in lines[0]["children"]


def test_bootstrap_no_split_when_no_shrink(tmp_path):
    """File that grows or stays same → no family written."""
    from agentflow.reporting import code_size_bootstrap

    sha = "abc123"
    parent_sha = "parent000"

    def mock_run(cmd, cwd=None, capture_output=False, text=False):
        m = MagicMock()
        m.returncode = 0
        cmd_str = " ".join(cmd)
        if "log" in cmd_str and "--format=%H %aI" in cmd_str:
            m.stdout = f"{sha} 2026-06-01T12:00:00+00:00\n"
        elif "diff-tree" in cmd_str and sha in cmd_str:
            m.stdout = "M\tagentflow.py\nA\tagentflow/module_a.py\n"
        elif "rev-parse" in cmd_str:
            m.stdout = f"{parent_sha}\n"
        elif "show" in cmd_str and parent_sha in cmd_str:
            m.stdout = "line\n" * 100  # 100 lines before
        elif "show" in cmd_str and sha in cmd_str:
            m.stdout = "line\n" * 80   # 80 after → only 20% shrink, < 50%
        else:
            m.stdout = ""
        return m

    with patch("agentflow.reporting.code_size_bootstrap.subprocess.run", side_effect=mock_run):
        families_path = tmp_path / ".agentflow" / "file_families.jsonl"
        code_size_bootstrap.bootstrap(cwd=tmp_path, families_path=families_path)

    if families_path.exists():
        lines = [ln for ln in families_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 0


def test_bootstrap_idempotent(tmp_path):
    """Running twice with same data produces no duplicate entries."""
    from agentflow.reporting import code_size_bootstrap

    sha = "abc123def456"
    parent_sha = "parent000sha"

    def mock_run(cmd, cwd=None, capture_output=False, text=False):
        m = MagicMock()
        m.returncode = 0
        cmd_str = " ".join(cmd)
        if "log" in cmd_str and "--format=%H %aI" in cmd_str:
            m.stdout = f"{sha} 2026-06-01T12:00:00+00:00\n"
        elif "diff-tree" in cmd_str and sha in cmd_str:
            m.stdout = "M\tagentflow.py\nA\tagentflow/module_a.py\n"
        elif "rev-parse" in cmd_str:
            m.stdout = f"{parent_sha}\n"
        elif "show" in cmd_str and parent_sha in cmd_str:
            m.stdout = "line\n" * 300
        elif "show" in cmd_str and sha in cmd_str:
            m.stdout = "line\n" * 100
        else:
            m.stdout = ""
        return m

    families_path = tmp_path / ".agentflow" / "file_families.jsonl"
    with patch("agentflow.reporting.code_size_bootstrap.subprocess.run", side_effect=mock_run):
        code_size_bootstrap.bootstrap(cwd=tmp_path, families_path=families_path)
        code_size_bootstrap.bootstrap(cwd=tmp_path, families_path=families_path)

    lines = [ln for ln in families_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1  # No duplicates

"""Tests for agentflow/shell/orchestrate_cache.py — T-170."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from agentflow.shell.orchestrate_cache import build_cache, is_cache_stale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tasks_json(path: Path, tasks: list[dict] | None = None) -> Path:
    if tasks is None:
        tasks = [
            {
                "task_id": "T-100",
                "title": "First pending task",
                "description": "long description text that should not appear in cache",
                "owns": ["agentflow/shell/foo.py"],
                "status": "pending",
                "depends_on": ["T-099"],
            },
            {
                "task_id": "T-101",
                "title": "Second pending task",
                "description": "another long description",
                "owns": ["agentflow/shell/bar.py"],
                "status": "pending",
            },
            {
                "task_id": "T-099",
                "title": "Complete task",
                "description": "done",
                "owns": [],
                "status": "complete",
            },
        ]
    p = path / "tasks.json"
    p.write_text(json.dumps({"tasks": tasks}))
    return p


def _make_execution_plan(path: Path) -> Path:
    content = "# Execution Plan\n\n## M1\n\n### Round Table\n| R1 | T-100 | ships |\n"
    p = path / "execution_plan.md"
    p.write_text(content)
    return p


def _make_design_status(path: Path, unresolved: int = 0) -> Path:
    rows = "| Item | Status | Decision |\n|---|---|---|\n"
    for i in range(unresolved):
        rows += f"| Decision {i} | UNRESOLVED | pending |\n"
    rows += "| Resolved item | RESOLVED | done |\n"
    p = path / "design_status.md"
    p.write_text(f"# Design Decisions\n\n{rows}")
    return p


def _make_calibration(home_dir: Path, ewma_mean: float = 58969.0,
                       ewma_cv: float = 0.0, sample_count: int = 1) -> Path:
    cal_dir = home_dir / ".agentflow"
    cal_dir.mkdir(parents=True, exist_ok=True)
    cal = {
        "ewma_mean_tokens": ewma_mean,
        "ewma_cv": ewma_cv,
        "sample_count": sample_count,
        "ewma_alpha": 0.3,
    }
    p = cal_dir / "rate_calibration_claude.json"
    p.write_text(json.dumps(cal))
    return p


def _setup_project(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Return (project_root, fake_home)."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    _make_tasks_json(project_root)
    _make_execution_plan(project_root)
    _make_design_status(project_root, unresolved=2)
    _make_calibration(fake_home)

    return project_root, fake_home


# ---------------------------------------------------------------------------
# Test 1: build_cache writes correct schema
# ---------------------------------------------------------------------------

def test_build_cache_correct_schema(tmp_path, monkeypatch):
    project_root, _ = _setup_project(tmp_path, monkeypatch)

    cache_path = build_cache(project_root)

    assert cache_path.exists(), "cache file must be written"
    with open(cache_path) as f:
        cache = json.load(f)

    required_keys = {
        "pending_tasks",
        "all_pending_count",
        "unresolved_design_count",
        "ewma_mean_tokens",
        "ewma_cv",
        "sample_count",
        "source_mtimes",
    }
    assert required_keys <= set(cache.keys()), (
        f"Missing keys: {required_keys - set(cache.keys())}"
    )
    assert cache["all_pending_count"] == 2
    assert cache["unresolved_design_count"] == 2
    assert cache["ewma_mean_tokens"] == 58969.0
    assert cache["ewma_cv"] == 0.0
    assert cache["sample_count"] == 1
    assert isinstance(cache["source_mtimes"], dict)
    assert len(cache["source_mtimes"]) > 0


# ---------------------------------------------------------------------------
# Test 2: pending_tasks shape — only task_id, title, depends_on
# ---------------------------------------------------------------------------

def test_pending_tasks_shape(tmp_path, monkeypatch):
    project_root, _ = _setup_project(tmp_path, monkeypatch)

    cache_path = build_cache(project_root)
    with open(cache_path) as f:
        cache = json.load(f)

    assert len(cache["pending_tasks"]) == 2, "should have 2 pending tasks"
    allowed_keys = {"task_id", "title", "depends_on"}
    for task in cache["pending_tasks"]:
        assert set(task.keys()) == allowed_keys, (
            f"Task has unexpected keys: {set(task.keys()) - allowed_keys}"
        )
        # specifically must NOT have description, owns, status
        assert "description" not in task
        assert "owns" not in task
        assert "status" not in task

    # T-100 has depends_on set
    t100 = next(t for t in cache["pending_tasks"] if t["task_id"] == "T-100")
    assert t100["depends_on"] == ["T-099"]

    # T-101 has no depends_on → defaults to []
    t101 = next(t for t in cache["pending_tasks"] if t["task_id"] == "T-101")
    assert t101["depends_on"] == []


# ---------------------------------------------------------------------------
# Test 3: is_cache_stale returns True when cache absent
# ---------------------------------------------------------------------------

def test_is_cache_stale_when_absent(tmp_path, monkeypatch):
    project_root, _ = _setup_project(tmp_path, monkeypatch)
    # No cache written
    assert is_cache_stale(project_root) is True


# ---------------------------------------------------------------------------
# Test 4: is_cache_stale returns True when source file newer than cache
# ---------------------------------------------------------------------------

def test_is_cache_stale_when_source_newer(tmp_path, monkeypatch):
    project_root, _ = _setup_project(tmp_path, monkeypatch)

    # Set all sources to past mtime
    past = time.time() - 100
    tasks_path = project_root / "tasks.json"
    execution_path = project_root / "execution_plan.md"
    os.utime(tasks_path, (past, past))
    os.utime(execution_path, (past, past))

    build_cache(project_root)

    # Now bump tasks.json to a future mtime
    future = time.time() + 10
    os.utime(tasks_path, (future, future))

    assert is_cache_stale(project_root) is True


# ---------------------------------------------------------------------------
# Test 5: is_cache_stale returns False when all sources older than cache
# ---------------------------------------------------------------------------

def test_is_cache_stale_when_fresh(tmp_path, monkeypatch):
    project_root, _ = _setup_project(tmp_path, monkeypatch)

    # Set all source files to past mtime before building
    past = time.time() - 100
    for fname in ("tasks.json", "execution_plan.md", "design_status.md"):
        p = project_root / fname
        if p.exists():
            os.utime(p, (past, past))
    state_p = project_root / ".agentflow" / "state.json"
    if state_p.exists():
        os.utime(state_p, (past, past))

    build_cache(project_root)
    # Cache was written after the past mtime sources — should be fresh
    assert is_cache_stale(project_root) is False


# ---------------------------------------------------------------------------
# Test 6: build_cache is idempotent
# ---------------------------------------------------------------------------

def test_build_cache_idempotent(tmp_path, monkeypatch):
    project_root, _ = _setup_project(tmp_path, monkeypatch)

    cache_path_1 = build_cache(project_root)
    with open(cache_path_1) as f:
        first = json.load(f)

    # Freeze source mtimes so second call records same values
    sources = [
        project_root / "tasks.json",
        project_root / "execution_plan.md",
        project_root / "design_status.md",
        project_root / ".agentflow" / "state.json",
    ]
    for p in sources:
        if p.exists():
            mtime = p.stat().st_mtime
            os.utime(p, (mtime, mtime))

    cache_path_2 = build_cache(project_root)
    with open(cache_path_2) as f:
        second = json.load(f)

    # Non-mtime fields must be identical
    non_mtime_keys = [k for k in first if k != "source_mtimes"]
    for key in non_mtime_keys:
        assert first[key] == second[key], f"Key '{key}' differs between runs"

    assert cache_path_1 == cache_path_2, "cache written to same path"


# ---------------------------------------------------------------------------
# Edge: calibration file absent → defaults
# ---------------------------------------------------------------------------

def test_build_cache_defaults_when_no_calibration(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    fake_home = tmp_path / "home_nocal"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    _make_tasks_json(project_root)
    _make_execution_plan(project_root)
    _make_design_status(project_root)
    # No calibration file, no state.json

    cache_path = build_cache(project_root)
    with open(cache_path) as f:
        cache = json.load(f)

    assert cache["ewma_mean_tokens"] == 2500
    assert cache["ewma_cv"] == 0.0
    assert cache["sample_count"] == 0

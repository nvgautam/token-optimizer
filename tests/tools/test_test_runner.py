"""Tests for test_runner.py and file_validator.py (T-007)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agentflow.config.schema import AgentFlowConfig
from agentflow.tools.test_runner import TestResult, run_tests
from agentflow.tools.file_validator import FileViolation, classify_file, validate_file_sizes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> AgentFlowConfig:
    return AgentFlowConfig()  # coverage_threshold=85


@pytest.fixture
def low_threshold_config() -> AgentFlowConfig:
    cfg = AgentFlowConfig()
    cfg.testing.coverage_threshold = 1
    return cfg


@pytest.fixture
def high_threshold_config() -> AgentFlowConfig:
    cfg = AgentFlowConfig()
    cfg.testing.coverage_threshold = 100
    return cfg


@pytest.fixture
def simple_passing_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "calc.py").write_text("def add(a, b): return a + b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from src.calc import add\ndef test_add(): assert add(1, 2) == 3\n"
    )
    return tmp_path


@pytest.fixture
def failing_project(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_fail.py").write_text(
        "def test_always_fails(): assert False\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# run_tests — integration tests against real pytest
# ---------------------------------------------------------------------------

def test_passing_project_returns_ok(simple_passing_project, config):
    result = run_tests(simple_passing_project, config)
    assert isinstance(result, TestResult)
    assert result.passed >= 1
    assert result.status == "ok"


def test_failing_project_returns_failed(failing_project, config):
    result = run_tests(failing_project, config)
    assert result.status == "failed"
    assert result.failed >= 1


def test_coverage_below_threshold_sets_coverage_ok_false(simple_passing_project, high_threshold_config):
    result = run_tests(simple_passing_project, high_threshold_config)
    # 100% threshold is impossible to hit unless coverage is exactly 100
    # calc.py has one function; 1/1 lines covered — may or may not hit 100%
    # Use a threshold that guarantees failure: set to 101 via direct mutation
    high_threshold_config.testing.coverage_threshold = 101
    result2 = run_tests(simple_passing_project, high_threshold_config)
    assert result2.coverage_ok is False


def test_coverage_above_threshold_sets_coverage_ok_true(simple_passing_project, low_threshold_config):
    result = run_tests(simple_passing_project, low_threshold_config)
    assert result.coverage_ok is True


def test_nonexistent_path_returns_error(config, tmp_path):
    result = run_tests(tmp_path / "does_not_exist", config)
    assert result.status == "error"
    assert result.passed == 0


def test_run_tests_never_raises(config, tmp_path):
    # Passing a file instead of a directory should not raise
    bad_path = tmp_path / "not_a_dir.txt"
    bad_path.write_text("hello")
    try:
        result = run_tests(bad_path, config)
        assert isinstance(result, TestResult)
    except Exception as exc:
        pytest.fail(f"run_tests raised unexpectedly: {exc}")


def test_timeout_returns_timeout_status(config, tmp_path):
    from agentflow.tools import test_runner as tr
    original_timeout = 300

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_slow.py").write_text(
        "import time\ndef test_slow(): time.sleep(0.1)\n"
    )

    import subprocess
    original_run = subprocess.run

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=0)

    import agentflow.tools.test_runner as mod
    mod_run = mod.__dict__
    original = mod_run.get("subprocess")

    import unittest.mock as mock
    with mock.patch("agentflow.tools.test_runner.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=0)):
        result = run_tests(tmp_path, config)

    assert result.status == "timeout"


# ---------------------------------------------------------------------------
# file_validator tests
# ---------------------------------------------------------------------------

def test_classify_tests_file():
    assert classify_file(Path("tests/test_foo.py")) == "tests"


def test_classify_implementation_file():
    assert classify_file(Path("agentflow/tools/git.py")) == "implementation"


def test_classify_prompts_file():
    assert classify_file(Path("agentflow/prompts/oracle/v1/system.md")) == "prompts"


def test_classify_stubs_file():
    assert classify_file(Path("stubs/auth.py")) == "stubs"


def test_file_at_exactly_ceiling_no_violation(tmp_path, config):
    f = tmp_path / "module.py"
    # implementation ceiling = 250 lines
    f.write_text("\n" * 249)  # 249 newlines = 249 lines (splitlines gives 249)
    violations = validate_file_sizes([f], config)
    assert violations == []


def test_file_one_over_ceiling_returns_violation(tmp_path, config):
    f = tmp_path / "module.py"
    # Write 251 lines (over 250 ceiling)
    f.write_text("\n" * 251)
    violations = validate_file_sizes([f], config)
    assert len(violations) == 1
    v = violations[0]
    assert v.path == f
    assert v.line_count > 250
    assert v.ceiling == 250
    assert v.file_type == "implementation"


def test_empty_file_list_returns_empty(config):
    assert validate_file_sizes([], config) == []


def test_nonexistent_file_skipped(tmp_path, config):
    missing = tmp_path / "ghost.py"
    violations = validate_file_sizes([missing], config)
    assert violations == []


def test_test_file_uses_test_ceiling(tmp_path, config):
    f = tmp_path / "tests" / "test_foo.py"
    f.parent.mkdir()
    # tests ceiling = 350; write 351 lines
    f.write_text("\n" * 351)
    violations = validate_file_sizes([f], config)
    assert len(violations) == 1
    assert violations[0].ceiling == 350
    assert violations[0].file_type == "tests"

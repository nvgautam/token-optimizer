"""Tests for T-010: worker context builder."""

from pathlib import Path
from unittest.mock import patch, call
import pytest

from agentflow.config.schema import AgentFlowConfig
from agentflow.worker.context_builder import build_context, _extract_arch_section, MAX_BUNDLE_CHARS

SAMPLE_TASK = {
    "task_id": "T-TEST",
    "title": "Test module",
    "description": "Build a test module.",
    "acceptance_criteria": "all tests green",
    "owns": ["agentflow/sample/module.py"],
    "reads": ["agentflow/config/loader.py"],
    "contracts": ["agentflow/sample/module.py"],
    "test_requirements": {
        "unit": ["returns correct result", "raises on invalid input"],
        "integration": [],
        "coverage_threshold": 85,
    },
    "security_constraints": ["no plaintext secrets"],
    "context_section": "architecture.md#context-bundle",
    "estimated_lines": 100,
}

ARCH_CONTENT = """# Architecture

## System components

Some content about components.

## Context bundle

The context bundle section content here.
Workers read this file.

## Task schema

Task schema content.
"""


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "architecture.md").write_text(ARCH_CONTENT)
    # create a stub contract file
    stub_dir = tmp_path / "agentflow" / "sample"
    stub_dir.mkdir(parents=True)
    (stub_dir / "module.py").write_text("def compute(): raise NotImplementedError\n")
    return tmp_path


@pytest.fixture
def config():
    return AgentFlowConfig()


def test_bundle_file_written(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    assert result.output_path.exists()
    assert result.output_path == project_root / ".agentflow" / "context" / "T-TEST.md"


def test_bundle_contains_task_section(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    assert "Build a test module" in result.content
    assert "all tests green" in result.content


def test_bundle_contains_owns_section(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    assert "agentflow/sample/module.py" in result.content
    assert "## OWNS" in result.content


def test_bundle_excludes_unrelated_files(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    # a file not in owns or reads should not appear as a section entry
    assert "agentflow/tools/git.py" not in result.content


def test_bundle_includes_test_strategy_when_present(project_root, config):
    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir(parents=True, exist_ok=True)
    (agentflow_dir / "test_strategy.md").write_text("Coverage: 85%. Mock all IO.")
    result = build_context(SAMPLE_TASK, project_root, config)
    assert "Coverage: 85%" in result.content
    assert "## TEST STRATEGY" in result.content


def test_bundle_includes_test_scenarios(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    assert "## TEST SCENARIOS" in result.content
    assert "returns correct result" in result.content
    assert "raises on invalid input" in result.content


def test_bundle_includes_security_constraints(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    assert "## SECURITY CONSTRAINTS" in result.content
    assert "no plaintext secrets" in result.content


def test_bundle_includes_config_section(project_root, config):
    result = build_context(SAMPLE_TASK, project_root, config)
    assert "## CONFIG" in result.content
    assert "claude-sonnet-4-6" in result.content
    assert "85%" in result.content


def test_token_estimate_metric_emitted(project_root, config):
    with patch("agentflow.worker.context_builder.emit_metric") as mock_emit:
        result = build_context(SAMPLE_TASK, project_root, config)
        mock_emit.assert_called_once()
        args, kwargs = mock_emit.call_args
        assert args[0] == "worker.context_built"
        assert kwargs.get("task_id") == "T-TEST"
        assert kwargs.get("status") == "ok"
    assert result.token_estimate == len(result.content) // 4


def test_oversized_bundle_raises_value_error(project_root, config):
    big_task = dict(SAMPLE_TASK)
    big_task["description"] = "x" * (MAX_BUNDLE_CHARS + 1)
    with pytest.raises(ValueError, match="exceeds"):
        build_context(big_task, project_root, config)


def test_extract_arch_section_returns_correct_section():
    section = _extract_arch_section(ARCH_CONTENT, "architecture.md#context-bundle")
    assert "context bundle section content" in section.lower()
    assert "task schema content" not in section.lower()


def test_extract_arch_section_returns_full_when_anchor_not_found():
    result = _extract_arch_section(ARCH_CONTENT, "architecture.md#nonexistent-section")
    assert result == ARCH_CONTENT


def test_extract_arch_section_returns_full_when_no_anchor():
    result = _extract_arch_section(ARCH_CONTENT, None)
    assert result == ARCH_CONTENT

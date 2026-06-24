"""Tests for agentflow.oracle.artifact_generator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentflow.config.schema import AgentFlowConfig
from agentflow.oracle.artifact_generator import (
    _validate_tasks,
    _write_design_session,
    _write_test_strategy,
    generate_artifacts,
)


def default_config() -> AgentFlowConfig:
    return AgentFlowConfig()


VALID_TASKS = [
    {
        "task_id": "T-001",
        "title": "Module A",
        "owns": ["agentflow/a/module_a.py"],
        "estimated_lines": 100,
        "test_requirements": {"unit": ["does something"], "integration": [], "coverage_threshold": 85},
        "security_constraints": [],
        "depends_on": [],
    },
    {
        "task_id": "T-002",
        "title": "Module B",
        "owns": ["agentflow/b/module_b.py"],
        "estimated_lines": 80,
        "test_requirements": {"unit": [], "integration": [], "coverage_threshold": 85},
        "security_constraints": [],
        "depends_on": [],
    },
]

CONFLICT_TASKS = [
    {"task_id": "T-001", "owns": ["agentflow/shared.py"], "estimated_lines": 50,
     "test_requirements": {}, "security_constraints": []},
    {"task_id": "T-002", "owns": ["agentflow/shared.py"], "estimated_lines": 50,
     "test_requirements": {}, "security_constraints": []},
]

OVERSIZE_TASKS = [
    {"task_id": "T-001", "owns": ["agentflow/big.py"], "estimated_lines": 9999,
     "test_requirements": {}, "security_constraints": []},
]


def test_validate_tasks_raises_on_shared_owned_file():
    with pytest.raises(ValueError, match="Ownership conflict"):
        _validate_tasks(CONFLICT_TASKS, default_config())


def test_validate_tasks_raises_on_size_violation():
    with pytest.raises(ValueError, match="ceiling"):
        _validate_tasks(OVERSIZE_TASKS, default_config())


def test_validate_tasks_passes_for_valid_tasks():
    _validate_tasks(VALID_TASKS, default_config())  # must not raise


def test_write_design_session_writes_nonempty_file(tmp_path):
    history = [
        {"role": "user", "content": "We need a payments service."},
        {"role": "assistant", "content": "- Use PostgreSQL for persistence."},
    ]
    dest = tmp_path / ".agentflow" / "design_session.md"
    _write_design_session(history, dest)
    assert dest.exists()
    content = dest.read_text()
    assert len(content) > 50


def test_write_test_strategy_contains_coverage_or_test(tmp_path):
    history = [{"role": "user", "content": "We need 90% coverage."}]
    dest = tmp_path / ".agentflow" / "test_strategy.md"
    _write_test_strategy(history, default_config(), dest)
    assert dest.exists()
    text = dest.read_text().lower()
    assert "coverage" in text or "test" in text


def test_generate_artifacts_calls_generate_contracts_once_per_task(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    arch_block = "```markdown\n# Architecture\nOverview here.\n```"
    tasks_block = json.dumps({"tasks": VALID_TASKS})
    response_text = f"{arch_block}\n\n```json\n{tasks_block}\n```"

    mock_content = MagicMock()
    mock_content.text = response_text
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    call_count = {"n": 0}

    def fake_generate_contracts(task, project_root):
        call_count["n"] += 1
        from agentflow.oracle.contract_generator import GeneratedArtifacts
        return GeneratedArtifacts()

    with patch("anthropic.Anthropic", return_value=mock_client), \
         patch("agentflow.oracle.artifact_generator.generate_contracts", side_effect=fake_generate_contracts):
        result = generate_artifacts(
            [{"role": "user", "content": "Build a payments service."}],
            tmp_path,
            default_config(),
        )

    assert call_count["n"] == len(VALID_TASKS)
    assert result["task_count"] == len(VALID_TASKS)
    assert (tmp_path / "architecture.md").exists()
    assert (tmp_path / "tasks.json").exists()


def test_generate_artifacts_raises_on_ownership_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    tasks_block = json.dumps({"tasks": CONFLICT_TASKS})
    response_text = f"```markdown\n# Arch\n```\n\n```json\n{tasks_block}\n```"

    mock_content = MagicMock()
    mock_content.text = response_text
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(ValueError, match="Ownership conflict"):
            generate_artifacts([], tmp_path, default_config())

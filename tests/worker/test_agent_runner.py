"""Tests for T-011: headless worker agent runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentflow.config.schema import AgentFlowConfig
from agentflow.worker.agent_runner import (
    MAX_RESTARTS,
    WorkerResult,
    WorkerResultStatus,
    run_worker,
)


@pytest.fixture
def config():
    return AgentFlowConfig()


@pytest.fixture
def task(tmp_path):
    return {
        "task_id": "T-TEST",
        "title": "Test task",
        "description": "Build a thing",
        "owns": ["agentflow/sample/module.py"],
        "reads": [],
        "test_requirements": {"unit": [], "integration": [], "coverage_threshold": 85},
        "security_constraints": [],
        "context_section": None,
    }


@pytest.fixture(autouse=True)
def mock_git_ops():
    with patch("agentflow.tools.git.create_worktree") as mock_create, \
         patch("agentflow.tools.git.commit_files") as mock_commit, \
         patch("agentflow.tools.git.push_branch") as mock_push:
        yield mock_create, mock_commit, mock_push



def _make_block(name, block_id, inputs):
    """Create a mock tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = block_id
    block.input = inputs
    return block


def _make_text_block(text="Done"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_response(blocks, stop_reason="tool_use", input_tokens=100, output_tokens=50):
    resp = MagicMock()
    resp.content = blocks
    resp.stop_reason = stop_reason
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


def _make_client(*responses):
    """Create a mock anthropic client that returns responses in sequence."""
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


def _patch_env(monkeypatch, key="test-api-key"):
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_returns_error_when_api_key_absent(monkeypatch, task, config, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = run_worker(task, tmp_path, tmp_path, config)
    assert isinstance(result, WorkerResult)
    assert result.status == WorkerResultStatus.ERROR
    assert "ANTHROPIC_API_KEY" in result.message


def test_returns_pr_opened_when_agent_opens_pr(monkeypatch, task, config, tmp_path):
    _patch_env(monkeypatch)
    # Sequence: run_tests (ok) → open_pr → done
    run_tests_block = _make_block("run_tests", "id1", {})
    open_pr_block = _make_block("open_pr", "id2", {"title": "feat", "body": "body"})

    resp1 = _make_response([run_tests_block])
    resp2 = _make_response([open_pr_block])

    mock_client = _make_client(resp1, resp2)

    with patch("agentflow.worker.agent_runner.TokenTracker") as MockTracker, \
         patch("anthropic.Anthropic", return_value=mock_client), \
         patch("agentflow.tools.test_runner.run_tests") as mock_tests, \
         patch("agentflow.tools.github.create_pr", return_value=42):
        mock_tracker = MagicMock()
        mock_tracker.track_span.return_value = MagicMock(status=MagicMock(value="ok"))
        # Use real BudgetStatus
        from agentflow.telemetry.token_tracker import BudgetStatus
        mock_tracker.track_span.return_value.status = BudgetStatus.OK
        mock_tracker.session_total.return_value = 150
        MockTracker.return_value = mock_tracker

        mock_test_result = MagicMock()
        mock_test_result.status = "ok"
        mock_test_result.passed = 5
        mock_test_result.failed = 0
        mock_test_result.coverage_pct = 90.0
        mock_test_result.coverage_ok = True
        mock_test_result.output = "5 passed"
        mock_tests.return_value = mock_test_result

        result = run_worker(task, tmp_path, tmp_path, config)

    assert result.status == WorkerResultStatus.PR_OPENED
    assert result.pr_number == 42


def test_write_file_non_owned_returns_error_not_exception(task, config, tmp_path):
    from agentflow.worker.agent_runner import _WorkerSession
    from agentflow.telemetry.token_tracker import TokenTracker
    tracker = TokenTracker(tmp_path, config)
    session = _WorkerSession(task, tmp_path, tmp_path, config, tracker, None)
    result = session._write("not/owned/file.py", "content")
    assert "not owned" in result
    assert isinstance(result, str)


def test_read_file_path_traversal_returns_error(monkeypatch, task, config, tmp_path):
    _patch_env(monkeypatch)
    from agentflow.worker.agent_runner import _WorkerSession
    from agentflow.telemetry.token_tracker import TokenTracker

    tracker = TokenTracker(tmp_path, config)
    session = _WorkerSession(task, tmp_path, tmp_path, config, tracker, None)
    result = session._read("../../etc/passwd")
    assert "traversal" in result.lower() or "Error" in result


def test_escalated_after_max_restarts(monkeypatch, task, config, tmp_path):
    _patch_env(monkeypatch)
    from agentflow.telemetry.token_tracker import BudgetStatus

    call_count = 0
    def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.content = []
        resp.stop_reason = "tool_use"
        resp.usage.input_tokens = 100
        resp.usage.output_tokens = 50
        return resp

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = fake_create

    with patch("agentflow.worker.agent_runner.TokenTracker") as MockTracker, \
         patch("anthropic.Anthropic", return_value=mock_client):
        mock_tracker = MagicMock()
        mock_tracker.track_span.return_value.status = BudgetStatus.EXCEEDED
        mock_tracker.session_total.return_value = 50000
        MockTracker.return_value = mock_tracker

        result = run_worker(task, tmp_path, tmp_path, config)

    assert result.status == WorkerResultStatus.ESCALATED
    assert result.restarts == MAX_RESTARTS


def test_token_span_emitted_per_api_call(monkeypatch, task, config, tmp_path):
    _patch_env(monkeypatch)
    from agentflow.telemetry.token_tracker import BudgetStatus

    end_resp = _make_response([_make_text_block()], stop_reason="end_turn")
    mock_client = _make_client(end_resp)

    with patch("agentflow.worker.agent_runner.TokenTracker") as MockTracker, \
         patch("anthropic.Anthropic", return_value=mock_client):
        mock_tracker = MagicMock()
        mock_tracker.track_span.return_value.status = BudgetStatus.OK
        mock_tracker.session_total.return_value = 150
        MockTracker.return_value = mock_tracker

        run_worker(task, tmp_path, tmp_path, config)

    assert mock_tracker.track_span.call_count >= 1
    call_args = mock_tracker.track_span.call_args
    assert call_args[0][1] == "worker.api_call"


def test_run_worker_never_raises(monkeypatch, task, config, tmp_path):
    _patch_env(monkeypatch)
    with patch("anthropic.Anthropic", side_effect=RuntimeError("boom")):
        result = run_worker(task, tmp_path, tmp_path, config)
    assert isinstance(result, WorkerResult)
    assert result.status == WorkerResultStatus.ERROR


def test_tokens_consumed_equals_session_total(monkeypatch, task, config, tmp_path):
    _patch_env(monkeypatch)
    from agentflow.telemetry.token_tracker import BudgetStatus

    end_resp = _make_response([_make_text_block()], stop_reason="end_turn",
                               input_tokens=200, output_tokens=80)
    mock_client = _make_client(end_resp)

    with patch("agentflow.worker.agent_runner.TokenTracker") as MockTracker, \
         patch("anthropic.Anthropic", return_value=mock_client):
        mock_tracker = MagicMock()
        mock_tracker.track_span.return_value.status = BudgetStatus.OK
        mock_tracker.session_total.return_value = 280
        MockTracker.return_value = mock_tracker

        result = run_worker(task, tmp_path, tmp_path, config)

    assert result.tokens_consumed == 280

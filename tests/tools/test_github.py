"""Unit tests for T-006: GitHub tools."""

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from agentflow.tools.github import (
    AuthError,
    CheckResult,
    GitHubAPIError,
    ReviewComment,
    create_pr,
    get_check_status,
    post_review_comments,
)


def _mock_client(status_code: int, json_data: dict, headers: dict | None = None):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = ""
    mock_resp.headers = headers or {}
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_ctx.post.return_value = mock_resp
    mock_ctx.get.return_value = mock_resp
    return mock_ctx


def test_create_pr_posts_correct_endpoint(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    mock_ctx = _mock_client(201, {"number": 42})
    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        result = create_pr("owner/repo", "feature", "main", "My PR", "body text")
    assert result == 42
    call_args = mock_ctx.post.call_args
    assert "/repos/owner/repo/pulls" in call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["head"] == "feature"
    assert payload["base"] == "main"


def test_post_review_comments_single_api_call(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    mock_ctx = _mock_client(200, {})
    comments = [
        ReviewComment(path="src/auth.py", line=10, body="Missing input validation"),
        ReviewComment(path="src/auth.py", line=25, body="Hardcoded secret"),
    ]
    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        post_review_comments("owner/repo", 7, comments)
    assert mock_ctx.post.call_count == 1
    call_args = mock_ctx.post.call_args
    assert "/pulls/7/reviews" in call_args[0][0]
    payload = call_args[1]["json"]
    assert len(payload["comments"]) == 2


def test_missing_github_token_raises_auth_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(AuthError):
        create_pr("owner/repo", "branch", "main", "title", "body")


def test_empty_github_token_raises_auth_error(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "")
    with pytest.raises(AuthError):
        create_pr("owner/repo", "branch", "main", "title", "body")


def test_4xx_response_raises_github_api_error(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    mock_ctx = _mock_client(422, {"message": "Unprocessable"})
    mock_ctx.post.return_value.text = "Unprocessable entity"
    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        with pytest.raises(GitHubAPIError) as exc_info:
            create_pr("owner/repo", "branch", "main", "title", "body")
    assert exc_info.value.status_code == 422


def test_429_triggers_retry_then_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    rate_resp = MagicMock()
    rate_resp.status_code = 429
    rate_resp.headers = {"Retry-After": "0"}
    rate_resp.text = "rate limited"

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_ctx.post.return_value = rate_resp

    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        with patch("agentflow.tools.github.time.sleep"):
            with pytest.raises(GitHubAPIError) as exc_info:
                create_pr("owner/repo", "branch", "main", "title", "body")
    assert mock_ctx.post.call_count == 2
    assert exc_info.value.status_code == 429


def test_invalid_repo_format_raises_value_error_before_network(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    with patch("agentflow.tools.github.httpx.Client") as mock_client_cls:
        with pytest.raises(ValueError, match="Invalid repo format"):
            create_pr("not-valid-format", "branch", "main", "title", "body")
    mock_client_cls.assert_not_called()


def test_token_not_in_log_output(monkeypatch, caplog):
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret-token-abc123")
    mock_ctx = _mock_client(201, {"number": 1})
    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        with caplog.at_level(logging.DEBUG, logger="agentflow.tools.github"):
            create_pr("owner/repo", "branch", "main", "title", "body")
    for record in caplog.records:
        assert "super-secret-token-abc123" not in record.getMessage()


def test_get_check_status_returns_success(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    pr_resp = MagicMock()
    pr_resp.status_code = 200
    pr_resp.json.return_value = {"head": {"sha": "abc123"}}
    pr_resp.text = ""

    checks_resp = MagicMock()
    checks_resp.status_code = 200
    checks_resp.json.return_value = {
        "check_runs": [
            {"conclusion": "success"},
            {"conclusion": "success"},
        ]
    }
    checks_resp.text = ""

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_ctx.get.side_effect = [pr_resp, checks_resp]

    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        result = get_check_status("owner/repo", 5)

    assert isinstance(result, CheckResult)
    assert result.state == "success"
    assert len(result.checks) == 2


def test_get_check_status_returns_failure(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    pr_resp = MagicMock()
    pr_resp.status_code = 200
    pr_resp.json.return_value = {"head": {"sha": "deadbeef"}}
    pr_resp.text = ""

    checks_resp = MagicMock()
    checks_resp.status_code = 200
    checks_resp.json.return_value = {
        "check_runs": [{"conclusion": "failure"}, {"conclusion": "success"}]
    }
    checks_resp.text = ""

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_ctx.get.side_effect = [pr_resp, checks_resp]

    with patch("agentflow.tools.github.httpx.Client", return_value=mock_ctx):
        result = get_check_status("owner/repo", 5)

    assert result.state == "failure"

"""Tests for T-012: code reviewer agent."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agentflow.config.loader import load_config
from agentflow.reviewer.code_reviewer import (
    CodeReviewFinding,
    ReviewResult,
    review_pr,
)

SAMPLE_DIFF = """\
--- a/agentflow/sample/module.py
+++ b/agentflow/sample/module.py
@@ -1,3 +1,12 @@
+def compute(x, y):
+    raise NotImplementedError
+
+def dangerous():
+    import subprocess
+    subprocess.run("ls", shell=True)
+
+def bare():
+    try:
+        pass
+    except:
+        pass
"""

EMPTY_DIFF = ""


@pytest.fixture
def config(tmp_path):
    return load_config(tmp_path)


def _run(diff, config, contract_paths=None, monkeypatch=None, token="test-token"):
    if monkeypatch and token:
        monkeypatch.setenv("GITHUB_TOKEN", token)
    elif monkeypatch:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch("agentflow.reviewer.code_reviewer.post_review_comments"):
        return review_pr("owner/repo", 1, diff, contract_paths or [], "", config)


def test_shell_true_triggers_critical(config, monkeypatch):
    result = _run(SAMPLE_DIFF, config, monkeypatch=monkeypatch)
    criticals = [f for f in result.findings if f.severity == "CRITICAL" and "shell" in f.message]
    assert len(criticals) >= 1


def test_bare_except_triggers_high(config, monkeypatch):
    result = _run(SAMPLE_DIFF, config, monkeypatch=monkeypatch)
    highs = [f for f in result.findings if f.severity == "HIGH" and "except" in f.message.lower()]
    assert len(highs) >= 1


def test_not_implemented_in_non_test_triggers_high(config, monkeypatch):
    result = _run(SAMPLE_DIFF, config, monkeypatch=monkeypatch)
    ni = [f for f in result.findings if "NotImplementedError" in f.message]
    assert len(ni) >= 1
    assert any(f.severity in ("HIGH", "CRITICAL") for f in ni)


def test_not_implemented_in_contract_triggers_critical(config, monkeypatch):
    result = _run(
        SAMPLE_DIFF, config,
        contract_paths=[Path("agentflow/sample/module.py")],
        monkeypatch=monkeypatch,
    )
    criticals = [f for f in result.findings if f.severity == "CRITICAL" and f.category == "contract"]
    assert len(criticals) >= 1


def test_empty_diff_returns_zero_issues(config, monkeypatch):
    result = _run(EMPTY_DIFF, config, monkeypatch=monkeypatch)
    assert result.issues_count == 0
    assert result.findings == []


def test_findings_posted_when_token_set(config, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    with patch("agentflow.reviewer.code_reviewer.post_review_comments") as mock_post:
        result = review_pr("owner/repo", 1, SAMPLE_DIFF, [], "", config)
    assert result.posted is True
    mock_post.assert_called_once()


def test_posted_false_when_token_absent(config, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch("agentflow.reviewer.code_reviewer.post_review_comments") as mock_post:
        result = review_pr("owner/repo", 1, SAMPLE_DIFF, [], "", config)
    assert result.posted is False
    mock_post.assert_not_called()


def test_severity_distribution_counts_correct(config, monkeypatch):
    result = _run(SAMPLE_DIFF, config, monkeypatch=monkeypatch)
    dist = result.severity_distribution
    total = sum(dist.values())
    assert total == result.issues_count
    assert dist["CRITICAL"] >= 0 and dist["HIGH"] >= 0


def test_issues_count_equals_len_findings(config, monkeypatch):
    result = _run(SAMPLE_DIFF, config, monkeypatch=monkeypatch)
    assert result.issues_count == len(result.findings)


def test_file_exceeding_ceiling_triggers_high(config, tmp_path, monkeypatch):
    big_file = tmp_path / "agentflow" / "sample" / "big.py"
    big_file.parent.mkdir(parents=True)
    big_file.write_text("\n" * 300)
    diff = f"--- a/agentflow/sample/big.py\n+++ b/{big_file}\n@@ -1 +1 @@\n+x = 1\n"
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with patch("agentflow.reviewer.code_reviewer.post_review_comments"):
        result = review_pr("owner/repo", 1, diff, [], "", config)
    size_findings = [f for f in result.findings if f.category == "architecture"]
    assert len(size_findings) >= 1
    assert size_findings[0].severity == "HIGH"

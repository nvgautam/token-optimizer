"""Tests for T-013: security reviewer agent."""

from unittest.mock import patch

import pytest

from agentflow.config.loader import load_config
from agentflow.reviewer.security_reviewer import (
    SecurityReviewResult,
    review_security,
)

DIFF_WITH_SECRET = """\
--- a/agentflow/config/loader.py
+++ b/agentflow/config/loader.py
@@ -1,2 +1,3 @@
+API_KEY = "sk-abc123supersecretkey99"
+password = "hunter2password"
"""

DIFF_WITH_SHELL = """\
--- a/agentflow/tools/runner.py
+++ b/agentflow/tools/runner.py
@@ -1,2 +1,2 @@
+subprocess.run("ls -la", shell=True)
"""

CLEAN_DIFF = """\
--- a/agentflow/sample.py
+++ b/agentflow/sample.py
@@ -1 +1,2 @@
+def add(a, b): return a + b
"""

DIFF_WITH_COMPLIANCE_VIOLATION = """\
--- a/agentflow/auth.py
+++ b/agentflow/auth.py
@@ -1 +1,2 @@
+logging.info(f"User password: {password}")
"""


@pytest.fixture
def config(tmp_path):
    return load_config(tmp_path)


def test_hardcoded_secret_triggers_critical(config):
    result = review_security("owner/repo", 1, DIFF_WITH_SECRET, [], config)
    assert result.critical_count >= 1
    criticals = [f for f in result.findings if f.severity == "CRITICAL"]
    assert any(f.category == "secret" for f in criticals)


def test_secret_message_does_not_contain_secret_value(config):
    result = review_security("owner/repo", 1, DIFF_WITH_SECRET, [], config)
    secret_findings = [f for f in result.findings if f.category == "secret"]
    assert secret_findings
    for finding in secret_findings:
        assert "sk-abc123supersecretkey99" not in finding.message
        assert "hunter2password" not in finding.message


def test_shell_true_triggers_critical(config):
    result = review_security("owner/repo", 1, DIFF_WITH_SHELL, [], config)
    assert result.critical_count >= 1
    assert any(f.category == "injection" for f in result.findings if f.severity == "CRITICAL")


def test_clean_diff_returns_zero_criticals_and_highs(config):
    result = review_security("owner/repo", 1, CLEAN_DIFF, [], config)
    assert result.critical_count == 0
    assert result.high_count == 0


def test_compliance_constraint_violation_references_constraint(config):
    constraints = ["no plaintext secrets in logs"]
    result = review_security("owner/repo", 1, DIFF_WITH_COMPLIANCE_VIOLATION, constraints, config)
    compliance_findings = [f for f in result.findings if f.category == "compliance"]
    assert compliance_findings
    assert any("no plaintext secrets in logs" in f.message for f in compliance_findings)


def test_posted_false_when_github_token_absent(monkeypatch, config):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = review_security("owner/repo", 1, DIFF_WITH_SECRET, [], config)
    assert result.posted is False


def test_posted_true_when_github_token_set(monkeypatch, config):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    with patch("agentflow.reviewer.security_reviewer.post_review_comments"):
        result = review_security("owner/repo", 1, DIFF_WITH_SECRET, [], config)
    assert result.posted is True


def test_review_security_never_raises(config):
    result = review_security("owner/repo", 1, "not a diff at all !!!", [], config)
    assert isinstance(result, SecurityReviewResult)


def test_critical_and_high_counts_match_findings(config):
    result = review_security("owner/repo", 1, DIFF_WITH_SECRET + DIFF_WITH_SHELL, [], config)
    actual_critical = sum(1 for f in result.findings if f.severity == "CRITICAL")
    actual_high = sum(1 for f in result.findings if f.severity == "HIGH")
    assert result.critical_count == actual_critical
    assert result.high_count == actual_high

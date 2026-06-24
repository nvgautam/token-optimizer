"""Security reviewer: rule-based OWASP checks on PR diffs."""

import os
import re
from dataclasses import dataclass, field

from agentflow.config.schema import AgentFlowConfig
from agentflow.tools.github import AuthError, ReviewComment, post_review_comments

_SECRET_RE = re.compile(
    r'(?i)(api_key|secret|password|token|passwd)\s*=\s*["\'][^"\']{8,}["\']'
)
_SHELL_RE = re.compile(r'shell\s*=\s*True')
_SQL_RE = re.compile(
    r'(?i)(execute|query|cursor\.execute)\s*\([^)]*(%s|\.format\(|f["\'])'
)
_PATH_OPEN_RE = re.compile(r'(open\(|Path\()(?!["\'])')

_COMPLIANCE_PATTERNS: dict[str, re.Pattern] = {
    "no plaintext": re.compile(r'(?i)(log|print).*\(.*?(password|secret|token)'),
    "no shell": re.compile(r'shell\s*=\s*True'),
    "rate limit": re.compile(r'(?i)rate.?limit'),
}


@dataclass
class SecurityFinding:
    file_path: str
    line: int
    severity: str
    category: str
    message: str


@dataclass
class SecurityReviewResult:
    pr_number: int
    critical_count: int
    high_count: int
    findings: list[SecurityFinding] = field(default_factory=list)
    posted: bool = False


def _parse_diff(diff: str) -> list[tuple[str, int, str]]:
    """Return (file_path, line_number, line_content) for every added line."""
    results: list[tuple[str, int, str]] = []
    current_file = ""
    line_num = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
        elif line.startswith("@@ "):
            m = re.search(r'\+(\d+)', line)
            line_num = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            line_num += 1
            results.append((current_file, line_num, line[1:]))
        elif not line.startswith("-"):
            line_num += 1
    return results


def _check_compliance(
    file_path: str,
    line_num: int,
    content: str,
    constraints: list[str],
) -> list[SecurityFinding]:
    findings = []
    for constraint in constraints:
        constraint_lower = constraint.lower()
        for keyword, pattern in _COMPLIANCE_PATTERNS.items():
            if keyword in constraint_lower and pattern.search(content):
                findings.append(SecurityFinding(
                    file_path=file_path,
                    line=line_num,
                    severity="CRITICAL",
                    category="compliance",
                    message=(
                        f"Compliance constraint violated: '{constraint}' "
                        f"at {file_path}:{line_num}"
                    ),
                ))
    return findings


def _scan_line(
    file_path: str,
    line_num: int,
    content: str,
    constraints: list[str],
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []

    if _SECRET_RE.search(content):
        findings.append(SecurityFinding(
            file_path=file_path,
            line=line_num,
            severity="CRITICAL",
            category="secret",
            message=f"Hardcoded secret detected at {file_path}:{line_num}. Remove and use env var.",
        ))

    if _SHELL_RE.search(content):
        findings.append(SecurityFinding(
            file_path=file_path,
            line=line_num,
            severity="CRITICAL",
            category="injection",
            message=f"Shell injection risk: shell=True at {file_path}:{line_num}. Use list args.",
        ))

    if _SQL_RE.search(content):
        findings.append(SecurityFinding(
            file_path=file_path,
            line=line_num,
            severity="HIGH",
            category="injection",
            message=f"Possible SQL injection via string formatting at {file_path}:{line_num}.",
        ))

    if _PATH_OPEN_RE.search(content):
        findings.append(SecurityFinding(
            file_path=file_path,
            line=line_num,
            severity="HIGH",
            category="validation",
            message=(
                f"Potential path traversal: open/Path with non-literal arg "
                f"at {file_path}:{line_num}. Validate input."
            ),
        ))

    findings.extend(_check_compliance(file_path, line_num, content, constraints))
    return findings


def review_security(
    repo: str,
    pr_number: int,
    diff: str,
    security_constraints: list[str],
    config: AgentFlowConfig,
) -> SecurityReviewResult:
    """Scan PR diff for security issues. Posts inline comments. Never raises."""
    try:
        added_lines = _parse_diff(diff)
        all_findings: list[SecurityFinding] = []
        for file_path, line_num, content in added_lines:
            all_findings.extend(_scan_line(file_path, line_num, content, security_constraints))

        critical = sum(1 for f in all_findings if f.severity == "CRITICAL")
        high = sum(1 for f in all_findings if f.severity == "HIGH")

        posted = False
        if all_findings:
            comments = [
                ReviewComment(path=f.file_path, line=f.line, body=f"**{f.severity}** [{f.category}]: {f.message}")
                for f in all_findings
            ]
            try:
                post_review_comments(repo, pr_number, comments)
                posted = True
            except AuthError:
                posted = False
            except Exception:
                posted = False

        return SecurityReviewResult(
            pr_number=pr_number,
            critical_count=critical,
            high_count=high,
            findings=all_findings,
            posted=posted,
        )
    except Exception:
        return SecurityReviewResult(
            pr_number=pr_number,
            critical_count=0,
            high_count=0,
            findings=[],
            posted=False,
        )

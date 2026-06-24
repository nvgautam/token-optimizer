"""Rule-based code reviewer: parses unified diffs, posts inline PR comments."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from agentflow.config.schema import AgentFlowConfig
from agentflow.tools.file_validator import classify_file, validate_file_sizes
from agentflow.tools.github import AuthError, ReviewComment, post_review_comments

_SHELL_TRUE = re.compile(r"shell\s*=\s*True")
_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
_NOT_IMPL = re.compile(r"raise\s+NotImplementedError")


@dataclass
class CodeReviewFinding:
    file_path: str
    line: int
    severity: str   # "CRITICAL" | "HIGH" | "LOW"
    category: str   # "contract" | "architecture" | "correctness" | "size"
    message: str


@dataclass
class ReviewResult:
    pr_number: int
    issues_count: int
    severity_distribution: dict[str, int]
    findings: list[CodeReviewFinding]
    posted: bool


def _parse_diff(diff: str) -> list[tuple[str, int, str]]:
    """Return (file_path, line_number, content) for each added line in a unified diff."""
    results: list[tuple[str, int, str]] = []
    current_file = ""
    current_line = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            current_line = 0
        elif raw.startswith("@@ "):
            m = re.search(r"\+(\d+)", raw)
            current_line = int(m.group(1)) - 1 if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            current_line += 1
            results.append((current_file, current_line, raw[1:]))
        elif not raw.startswith("-"):
            current_line += 1

    return results


def _check_lines(
    lines: list[tuple[str, int, str]],
    contract_paths: list[Path],
) -> list[CodeReviewFinding]:
    findings: list[CodeReviewFinding] = []
    contract_strs = {str(p) for p in contract_paths}

    for file_path, lineno, content in lines:
        is_test = "test" in file_path.lower()

        if _SHELL_TRUE.search(content):
            findings.append(CodeReviewFinding(
                file_path=file_path, line=lineno, severity="CRITICAL",
                category="correctness",
                message="shell=True is a shell injection risk — use list args.",
            ))

        if not is_test and _BARE_EXCEPT.search(content):
            findings.append(CodeReviewFinding(
                file_path=file_path, line=lineno, severity="HIGH",
                category="correctness",
                message="Bare `except:` swallows all exceptions — specify exception type.",
            ))

        if not is_test and _NOT_IMPL.search(content):
            severity = "CRITICAL" if file_path in contract_strs else "HIGH"
            findings.append(CodeReviewFinding(
                file_path=file_path, line=lineno, severity=severity,
                category="contract" if severity == "CRITICAL" else "correctness",
                message="raise NotImplementedError — stub not implemented.",
            ))

    return findings


def _check_file_sizes(
    diff: str,
    config: AgentFlowConfig,
) -> list[CodeReviewFinding]:
    seen: set[str] = set()
    findings: list[CodeReviewFinding] = []
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            path_str = raw[6:]
            if path_str in seen:
                continue
            seen.add(path_str)
            p = Path(path_str)
            if p.exists():
                violations = validate_file_sizes([p], config)
                for v in violations:
                    findings.append(CodeReviewFinding(
                        file_path=path_str, line=1, severity="HIGH",
                        category="architecture",
                        message=(
                            f"{path_str} is {v.line_count} lines "
                            f"(ceiling {v.ceiling} for type '{v.file_type}')."
                        ),
                    ))
    return findings


def _distribution(findings: list[CodeReviewFinding]) -> dict[str, int]:
    dist: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "LOW": 0}
    for f in findings:
        dist[f.severity] = dist.get(f.severity, 0) + 1
    return dist


def review_pr(
    repo: str,
    pr_number: int,
    diff: str,
    contract_paths: list[Path],
    architecture_section: str,
    config: AgentFlowConfig,
) -> ReviewResult:
    lines = _parse_diff(diff)
    findings = _check_lines(lines, contract_paths)
    findings += _check_file_sizes(diff, config)

    posted = False
    if findings and os.environ.get("GITHUB_TOKEN"):
        comments = [
            ReviewComment(
                path=f.file_path,
                line=f.line,
                body=f"**[{f.severity}] {f.category}**: {f.message}",
            )
            for f in findings
        ]
        try:
            post_review_comments(repo, pr_number, comments)
            posted = True
        except AuthError:
            posted = False

    return ReviewResult(
        pr_number=pr_number,
        issues_count=len(findings),
        severity_distribution=_distribution(findings),
        findings=findings,
        posted=posted,
    )

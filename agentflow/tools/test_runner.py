"""Run pytest with coverage inside a worktree. Always returns TestResult, never raises."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from agentflow.config.schema import AgentFlowConfig

_SUMMARY_RE = re.compile(
    r"(?:(\d+) passed)?[,\s]*(?:(\d+) failed)?[,\s]*(?:(\d+) error(?:s)?)?"
)
_COVERAGE_RE = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", re.MULTILINE)
_MAX_OUTPUT = 5000


@dataclass
class TestResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    coverage_pct: float = 0.0
    coverage_ok: bool = False
    status: str = "error"  # "ok" | "failed" | "timeout" | "error"
    output: str = ""


def _parse_summary(output: str) -> tuple[int, int, int]:
    """Extract (passed, failed, errors) from the last pytest summary line."""
    for line in reversed(output.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            m = _SUMMARY_RE.search(line)
            if m:
                return (
                    int(m.group(1) or 0),
                    int(m.group(2) or 0),
                    int(m.group(3) or 0),
                )
    return 0, 0, 0


def _parse_coverage(output: str) -> float:
    m = _COVERAGE_RE.search(output)
    return float(m.group(1)) if m else 0.0


def _validate_path(worktree_path: Path) -> None:
    resolved = worktree_path.resolve()
    if not resolved.exists():
        raise ValueError(f"worktree_path does not exist: {resolved}")


def run_tests(worktree_path: Path, config: AgentFlowConfig) -> TestResult:
    """Run pytest with coverage in worktree_path. Never raises."""
    try:
        _validate_path(worktree_path)
    except Exception as exc:
        return TestResult(status="error", output=str(exc))

    cmd = [
        "python", "-m", "pytest",
        "--tb=short",
        "--cov",
        "--cov-report=term-missing",
        "-q",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or "") + (exc.stderr or "")
        return TestResult(status="timeout", output=raw[:_MAX_OUTPUT])
    except Exception as exc:
        return TestResult(status="error", output=str(exc))

    combined = (proc.stdout or "") + (proc.stderr or "")
    output = combined[:_MAX_OUTPUT]

    passed, failed, errors = _parse_summary(combined)
    coverage_pct = _parse_coverage(combined)
    threshold = config.testing.coverage_threshold
    coverage_ok = coverage_pct >= threshold

    if failed > 0 or errors > 0:
        status = "failed"
    elif passed == 0 and failed == 0 and errors == 0:
        status = "error"
    else:
        status = "ok"

    return TestResult(
        passed=passed,
        failed=failed,
        errors=errors,
        coverage_pct=coverage_pct,
        coverage_ok=coverage_ok,
        status=status,
        output=output,
    )

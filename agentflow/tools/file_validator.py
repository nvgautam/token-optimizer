"""Validate file sizes against configured ceilings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentflow.config.schema import AgentFlowConfig


@dataclass
class FileViolation:
    path: Path
    line_count: int
    ceiling: int
    file_type: str  # "implementation" | "tests" | "prompts" | "stubs"


def classify_file(path: Path) -> str:
    """Classify a file path into a type for ceiling lookup."""
    parts = path.parts
    if "tests" in parts:
        return "tests"
    if "prompts" in parts:
        return "prompts"
    if "stubs" in parts:
        return "stubs"
    return "implementation"


def _ceiling_for(file_type: str, config: AgentFlowConfig) -> int:
    return getattr(config.file_limits, file_type)


def validate_file_sizes(files: list[Path], config: AgentFlowConfig) -> list[FileViolation]:
    """Return violations for files exceeding their ceiling. Empty list means clean."""
    violations: list[FileViolation] = []
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        line_count = len(text.splitlines())
        file_type = classify_file(path)
        ceiling = _ceiling_for(file_type, config)
        if line_count > ceiling:
            violations.append(FileViolation(
                path=path,
                line_count=line_count,
                ceiling=ceiling,
                file_type=file_type,
            ))
    return violations

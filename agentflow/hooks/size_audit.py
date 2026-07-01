#!/usr/bin/env python3
"""Standalone sweep: report every file exceeding its per-category line limit.

Complements the PostToolUse hook `size_check.py` (Claude-Code-specific —
fires only on Write/Edit). This script walks the whole repo so it also
catches (a) pre-existing files never touched by Claude's Write/Edit tool,
and (b) files written by Gemini CLI, which has no PostToolUse-equivalent
event to hook into. Not registered as a live hook — run manually or from
an orchestrator skill at milestone boundaries:

    python3 agentflow/hooks/size_audit.py [path]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

IMPLEMENTATION_LIMIT = 250
TESTS_LIMIT = 350
COMMANDS_LIMIT = 150

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".agentflow"}


@dataclass(frozen=True)
class Violation:
    path: str
    n_lines: int
    limit: int
    category: str


def _category_and_limit(rel_path: Path) -> tuple[str, int] | None:
    parts = rel_path.parts
    is_py = rel_path.suffix == ".py"
    is_commands = "commands" in parts
    is_tests = "tests" in parts

    if is_commands:
        return "commands", COMMANDS_LIMIT
    if is_tests and is_py:
        return "tests", TESTS_LIMIT
    if is_py:
        return "implementation", IMPLEMENTATION_LIMIT
    return None


def _is_stub(lines: list[str]) -> bool:
    n_lines = len(lines)
    if n_lines == 0:
        return False
    pass_lines = sum(1 for line in lines if line.strip() in ("pass", "..."))
    return pass_lines > 0.5 * n_lines


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def audit(root: Path | str) -> list[Violation]:
    """Walk `root` and return every file exceeding its category line limit.

    Stub files (>50% pass/ellipsis lines) are exempt, mirroring size_check.py.
    """
    root = Path(root).resolve()
    violations: list[Violation] = []

    for path in _iter_files(root):
        rel_path = path.relative_to(root)
        cat_limit = _category_and_limit(rel_path)
        if cat_limit is None:
            continue
        category, limit = cat_limit

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.splitlines()
        n_lines = len(lines)
        if n_lines == 0:
            continue

        if _is_stub(lines):
            continue

        if n_lines > limit:
            violations.append(
                Violation(
                    path=str(rel_path),
                    n_lines=n_lines,
                    limit=limit,
                    category=category,
                )
            )

    violations.sort(key=lambda v: v.path)
    return violations


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    root = argv[0] if argv else "."

    violations = audit(root)

    if not violations:
        print("size_audit: no violations found.")
        sys.exit(0)

    print(f"size_audit: {len(violations)} violation(s) found:")
    for v in violations:
        print(
            f"  FILE TOO LARGE: {v.path} is {v.n_lines} lines "
            f"(limit {v.limit}, category {v.category})"
        )
    sys.exit(1)


if __name__ == "__main__":
    main()

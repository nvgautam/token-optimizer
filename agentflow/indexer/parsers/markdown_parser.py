"""Markdown file parser for the symbol indexer.

Extracts H2 (##) and H3 (###) section headers from Markdown files.
Files with fewer than 50 lines return an empty list.
Unreadable files return an empty list without raising.
"""
from __future__ import annotations

import re
from pathlib import Path

from agentflow.indexer import IndexEntry

# Matches H2 or H3 only — not H1, H4, H5, H6.
_HEADER_RE = re.compile(r"^(#{2,3}) (.+)$")


def parse(path: Path) -> list[IndexEntry]:
    """Parse a Markdown file and return IndexEntry objects for H2/H3 headers.

    Args:
        path: Absolute or relative path to the Markdown file.

    Returns:
        List of IndexEntry objects, one per H2/H3 header.
        Returns [] if the file has fewer than 50 lines, is empty, or is unreadable.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = text.splitlines()
    if len(lines) < 50:
        return []

    # First pass: collect (line_number_1based, level, name) for each H2/H3
    headers: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if m:
            hashes, title = m.group(1), m.group(2)
            level = len(hashes)  # 2 or 3
            name = f"{hashes} {title}"
            headers.append((idx + 1, level, name))

    if not headers:
        return []

    total_lines = len(lines)
    entries: list[IndexEntry] = []

    for i, (start_line, level, name) in enumerate(headers):
        # Find end_line: the line before the next header at same or higher level
        end_line = total_lines  # default: EOF
        for j in range(i + 1, len(headers)):
            next_start, next_level, _ = headers[j]
            if next_level <= level:
                end_line = next_start - 1
                break

        entries.append(
            IndexEntry(
                name=name,
                kind="section",
                start_line=start_line,
                end_line=end_line,
                signature=None,
            )
        )

    return entries

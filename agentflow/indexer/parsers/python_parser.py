"""AST-based parser for Python source files — T-028a."""
from __future__ import annotations

import ast
from pathlib import Path

from agentflow.indexer import IndexEntry

MIN_LINES = 50


def parse(path: Path) -> list[IndexEntry]:
    """Parse *path* and return a list of IndexEntry for every indexable symbol.

    Indexed symbols:
    - Top-level functions  (kind='function')
    - Top-level classes    (kind='class')
    - Class methods        (kind='method', name='ClassName.method')

    Returns ``[]`` when the file has fewer than MIN_LINES lines, cannot be
    read, or contains invalid Python syntax.  Never raises.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = source.splitlines()
    if len(lines) < MIN_LINES:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    entries: list[IndexEntry] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entries.append(
                IndexEntry(
                    name=node.name,
                    kind="function",
                    start_line=node.lineno,
                    end_line=node.end_lineno,  # type: ignore[attr-defined]
                    signature=lines[node.lineno - 1].strip(),
                )
            )
        elif isinstance(node, ast.ClassDef):
            entries.append(
                IndexEntry(
                    name=node.name,
                    kind="class",
                    start_line=node.lineno,
                    end_line=node.end_lineno,  # type: ignore[attr-defined]
                    signature=None,
                )
            )
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    entries.append(
                        IndexEntry(
                            name=f"{node.name}.{item.name}",
                            kind="method",
                            start_line=item.lineno,
                            end_line=item.end_lineno,  # type: ignore[attr-defined]
                            signature=lines[item.lineno - 1].strip(),
                        )
                    )

    return entries

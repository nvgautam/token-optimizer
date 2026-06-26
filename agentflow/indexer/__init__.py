from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IndexEntry:
    """Represents a single indexed symbol from a source file."""

    name: str
    kind: str  # 'function' | 'class' | 'method'
    start_line: int
    end_line: int
    signature: str | None

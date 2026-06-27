from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ScanResult:
    indexed: int
    skipped: int
    duration_ms: int

    def __int__(self) -> int:
        return self.indexed

    def __index__(self) -> int:
        return self.indexed

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, int):
            return self.indexed == other
        if isinstance(other, ScanResult):
            return (self.indexed, self.skipped) == (other.indexed, other.skipped)
        return False


def scan(project_root: Path, config: Any = None) -> ScanResult:
    """Walk project tree, index all eligible files, populate cache. Idempotent."""
    start_time = time.perf_counter()
    
    project_root = Path(project_root).resolve()
    indexed_count = 0
    skipped_count = 0
    
    # Walk directory tree
    for root, dirs, files in os.walk(project_root):
        # Ignore common directories that should not be scanned
        ignored_dirs = {".git", ".venv", "node_modules", "__pycache__", ".agentflow", ".pytest_cache"}
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        
        for file in files:
            file_path = Path(root) / file
            suffix = file_path.suffix
            if suffix not in (".py", ".md"):
                skipped_count += 1
                continue
                
            try:
                contents = file_path.read_text(encoding="utf-8")
                lines = contents.splitlines()
            except OSError:
                skipped_count += 1
                continue
                
            if len(lines) < 50:
                skipped_count += 1
                continue
                
            # Eligible file: update index cache
            from agentflow.indexer.index_manager import update, get_cache_path
            
            try:
                # Cache path generation handles validation and security constraints
                cache_path = get_cache_path(file_path, project_root)
                
                # Check if it is already cached and up-to-date (idempotency check)
                if cache_path.exists() and cache_path.stat().st_mtime >= file_path.stat().st_mtime:
                    # Skip rewriting cache but still count as indexed
                    indexed_count += 1
                    continue
            except Exception:
                skipped_count += 1
                continue
                
            try:
                update(file_path, contents)
                indexed_count += 1
            except Exception:
                skipped_count += 1
                
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    return ScanResult(
        indexed=indexed_count,
        skipped=skipped_count,
        duration_ms=duration_ms
    )

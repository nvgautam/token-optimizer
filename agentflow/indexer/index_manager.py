from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from agentflow.indexer import IndexEntry


def find_project_root(path: Path) -> Path:
    """Find the project root containing .git, .agentflow, or pyproject.toml."""
    path = Path(path).resolve()
    curr = path if path.is_dir() else path.parent
    
    while True:
        if (curr / ".git").exists() or (curr / ".agentflow").exists() or (curr / "pyproject.toml").exists():
            return curr
        if curr.parent == curr:
            # Fallback to current working directory if path is under it, else use path parent
            cwd = Path.cwd().resolve()
            try:
                path.relative_to(cwd)
                return cwd
            except ValueError:
                return path.parent
        curr = curr.parent


def get_cache_path(path: Path, project_root: Path) -> Path:
    """Compute and validate the cache path for a given file."""
    cache_root = Path("~/.agentflow").expanduser().resolve()
    project_root = project_root.resolve()
    path = path.resolve()
    
    try:
        rel_path = path.relative_to(project_root)
    except ValueError:
        raise ValueError(f"Path {path} is not under project root {project_root}")
        
    project_hash = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()
    cache_path = cache_root / "cache" / project_hash / "index" / rel_path.parent / f"{rel_path.name}.idx"
    
    # Resolve and validate cache path parent/existence checks
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_cache = cache_path.resolve()
    
    # Security check: must resolve under ~/.agentflow
    try:
        resolved_cache.relative_to(cache_root)
    except ValueError:
        raise ValueError(f"Cache path {resolved_cache} must resolve under {cache_root}")
        
    # Security check: must be outside project tree
    is_inside = False
    try:
        resolved_cache.relative_to(project_root)
        is_inside = True
    except ValueError:
        pass
        
    if is_inside:
        raise ValueError(f"Cache path {resolved_cache} cannot resolve under project tree {project_root}")
        
    return resolved_cache


def parse_contents(path: Path, contents: str) -> list[IndexEntry]:
    """Parse the file contents using the appropriate parser without modifying the file."""
    suffix = path.suffix
    if suffix not in (".py", ".md"):
        return []
        
    with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False, encoding="utf-8") as f:
        f.write(contents)
        temp_path = Path(f.name)
    try:
        if suffix == ".py":
            from agentflow.indexer.parsers.python_parser import parse as parse_py
            return parse_py(temp_path)
        elif suffix == ".md":
            from agentflow.indexer.parsers.markdown_parser import parse as parse_md
            return parse_md(temp_path)
        return []
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def update(path: Path, contents: str) -> None:
    """Update the cache with the given file contents."""
    project_root = find_project_root(path)
    cache_path = get_cache_path(path, project_root)
    
    entries = parse_contents(path, contents)
    lines = [f"{entry.name}:{entry.start_line}-{entry.end_line}\n" for entry in entries]
    
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("".join(lines), encoding="utf-8")


def lookup(path: Path, symbol: str) -> IndexEntry | None:
    """Look up a symbol in the index entry for path."""
    entries = get_index(path)
    for entry in entries:
        if entry.name == symbol:
            return entry
    return None


def get_index(path: Path, project_root: Path | None = None) -> list[IndexEntry]:
    """Get all index entries for a file, regenerating them on cache miss/invalidation."""
    if project_root is not None:
        if path.is_dir() and not project_root.is_dir():
            p_root = path
            f_path = project_root
        else:
            f_path = path
            p_root = project_root
    else:
        f_path = path
        p_root = None

    if p_root is None:
        p_root = find_project_root(f_path)
        
    cache_path = get_cache_path(f_path, p_root)
    
    cache_miss = True
    if cache_path.exists() and f_path.exists():
        if cache_path.stat().st_mtime >= f_path.stat().st_mtime:
            cache_miss = False
            
    if cache_miss:
        if f_path.exists():
            try:
                contents = f_path.read_text(encoding="utf-8")
            except OSError:
                contents = ""
        else:
            contents = ""
        update(f_path, contents)
        
    if not cache_path.exists():
        return []
        
    try:
        idx_content = cache_path.read_text(encoding="utf-8")
    except OSError:
        return []
        
    entries = []
    lines = idx_content.splitlines()
    
    source_lines = []
    if f_path.exists():
        try:
            source_lines = f_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            pass
            
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        parts = line.split(":", 1)
        name = parts[0]
        if "-" not in parts[1]:
            continue
        start_str, end_str = parts[1].split("-", 1)
        try:
            start_line = int(start_str)
            end_line = int(end_str)
        except ValueError:
            continue
            
        kind = "function"
        signature = None
        
        if f_path.suffix == ".md":
            kind = "section"
        elif f_path.suffix == ".py":
            if "." in name:
                kind = "method"
            else:
                if 1 <= start_line <= len(source_lines):
                    start_line_content = source_lines[start_line - 1]
                    if start_line_content.strip().startswith("class "):
                        kind = "class"
                    else:
                        kind = "function"
                else:
                    kind = "function"
            
            if kind in ("function", "method"):
                if 1 <= start_line <= len(source_lines):
                    signature = source_lines[start_line - 1].strip()
                    
        entries.append(
            IndexEntry(
                name=name,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
                signature=signature,
            )
        )
        
    return entries


def update_index(project_root: Path, file_path: Path, contents: str) -> None:
    """Compatibility stub for update_index."""
    cache_path = get_cache_path(file_path, project_root)
    entries = parse_contents(file_path, contents)
    lines = [f"{entry.name}:{entry.start_line}-{entry.end_line}\n" for entry in entries]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("".join(lines), encoding="utf-8")

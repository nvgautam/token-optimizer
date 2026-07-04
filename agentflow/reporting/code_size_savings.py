"""Code-size savings: tokens saved by reading split files vs original (T-096)."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

LINES_TO_TOKENS = 4  # 1 line ≈ 4 tokens (consistent with rest of codebase)


def load_file_families(families_path: Path) -> dict[str, list[str]]:
    """Read .agentflow/file_families.jsonl; return {parent: [children]}."""
    if not families_path.exists():
        return {}
    result: dict[str, list[str]] = {}
    try:
        for line in families_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                parent = entry.get("parent", "")
                children = entry.get("children", [])
                if parent:
                    result[parent] = children
            except (json.JSONDecodeError, AttributeError):
                continue
    except OSError:
        pass
    return result


def _build_maps(families: dict[str, list[str]]) -> tuple[dict[str, str], dict[str, str]]:
    """Return (child_to_parent, member_to_parent) reverse maps."""
    child_to_parent: dict[str, str] = {}
    member_to_parent: dict[str, str] = {}
    for parent, children in families.items():
        member_to_parent[parent] = parent
        for child in children:
            child_to_parent[child] = parent
            member_to_parent[child] = parent
    return child_to_parent, member_to_parent


def _family_shadow_sizes(
    shadow_entries: list[dict],
    families: dict[str, list[str]],
    member_to_parent: dict[str, str],
) -> dict[str, int]:
    """Return {parent: shadow_size} where shadow_size = sum of max file_lines per member."""
    member_max: dict[str, int] = {}
    for e in shadow_entries:
        rel = e.get("rel", "")
        if rel in member_to_parent:
            fl = e.get("file_lines", 0)
            member_max[rel] = max(member_max.get(rel, 0), fl)
    result: dict[str, int] = {}
    for parent, children in families.items():
        result[parent] = sum(member_max.get(m, 0) for m in [parent] + children)
    return result


def compute_code_size_savings(
    shadow_entries: list[dict],
    families: dict[str, list[str]],
) -> dict:
    """Compute tokens saved by splitting large files.

    For each shadow entry where rel is a child in a family:
      shadow_size = sum of max file_lines across all family members (from shadow data).
      savings = max(shadow_size - file_lines, 0).
    Token approximation: 1 line = 4 tokens.

    Returns {"total_saved_tokens": int, "families_count": int, "reads_count": int}.
    """
    if not families:
        return {"total_saved_tokens": 0, "families_count": 0, "reads_count": 0}

    child_to_parent, member_to_parent = _build_maps(families)
    shadow_sizes = _family_shadow_sizes(shadow_entries, families, member_to_parent)

    total_saved_lines = 0
    reads_count = 0
    for e in shadow_entries:
        rel = e.get("rel", "")
        parent = child_to_parent.get(rel)  # children only, not parent files
        if parent is None:
            continue
        shadow_size = shadow_sizes.get(parent, 0)
        file_lines = e.get("file_lines", 0)
        total_saved_lines += max(0, shadow_size - file_lines)
        reads_count += 1

    return {
        "total_saved_tokens": total_saved_lines * LINES_TO_TOKENS,
        "families_count": len(families),
        "reads_count": reads_count,
    }


def daily_code_size_savings(
    shadow_entries: list[dict],
    families: dict[str, list[str]],
    days: int = 14,
) -> list[dict]:
    """Return [{"date": "YYYY-MM-DD", "code_size": int}, ...] for last `days` days."""
    if not families:
        return []

    child_to_parent, member_to_parent = _build_maps(families)
    shadow_sizes = _family_shadow_sizes(shadow_entries, families, member_to_parent)

    by_date: dict[str, int] = defaultdict(int)
    for e in shadow_entries:
        rel = e.get("rel", "")
        parent = child_to_parent.get(rel)
        if parent is None:
            continue
        d = e.get("ts", "")[:10]
        if not d:
            continue
        shadow_size = shadow_sizes.get(parent, 0)
        file_lines = e.get("file_lines", 0)
        saved_lines = max(0, shadow_size - file_lines)
        by_date[d] += saved_lines * LINES_TO_TOKENS

    all_dates = sorted(by_date.keys())
    return [{"date": d, "code_size": by_date[d]} for d in all_dates[-days:]]

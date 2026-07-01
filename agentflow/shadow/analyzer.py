#!/usr/bin/env python3
"""Shadow cost analyzer: measures token waste from unimplemented optimizations.

Usage: python agentflow/shadow/analyzer.py
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TOKENS_PER_CHAR = 0.25  # ~4 chars per token


def _tokens(chars: int) -> int:
    return int(chars * TOKENS_PER_CHAR)


def _load_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def get_bucketed_stats(project_root: Path, entries: list[dict], reads_files: set[str], mode: str = "aggregate") -> dict[str, int]:
    no_reread_val = 0
    targeted_reads_val = 0
    indexing_gap_val = 0
    state_docs_val = 0

    state_doc_names = {"architecture.md", "design_status.md", "execution_plan.md"}

    for e in entries:
        rel = e.get("rel", "")
        is_no_reread = rel in reads_files and e.get("offset") is None
        is_targeted = bool(e.get("idx_exists")) and e.get("offset") is None
        is_indexing_gap = not e.get("idx_exists") and e.get("file_lines", 0) >= 50 and e.get("offset") is None and rel not in state_doc_names
        is_state_doc = rel in state_doc_names

        if mode == "aggregate":
            if is_no_reread:
                no_reread_val += _tokens(e.get("file_chars", 0))
            elif is_targeted:
                file_chars = e.get("file_chars", 0)
                sections = max(e.get("idx_sections", 1), 1)
                avg_section_chars = file_chars / sections
                targeted_reads_val += _tokens(file_chars) - _tokens(int(avg_section_chars))
            elif is_indexing_gap:
                indexing_gap_val += _tokens(e.get("file_chars", 0))
            elif is_state_doc:
                state_docs_val += _tokens(e.get("file_chars", 0))
        else: # by-strategy
            if is_no_reread:
                no_reread_val += _tokens(e.get("file_chars", 0))
            if is_targeted:
                file_chars = e.get("file_chars", 0)
                sections = max(e.get("idx_sections", 1), 1)
                avg_section_chars = file_chars / sections
                targeted_reads_val += _tokens(file_chars) - _tokens(int(avg_section_chars))
            if is_indexing_gap:
                indexing_gap_val += _tokens(e.get("file_chars", 0))
            if is_state_doc:
                state_docs_val += _tokens(e.get("file_chars", 0))

    return {
        "no-reread": no_reread_val,
        "targeted-reads": targeted_reads_val,
        "indexing-gap": indexing_gap_val,
        "state-docs": state_docs_val
    }


def _report_targeted_reads(entries: list[dict]) -> int:
    """Symbol index + section-only loading: full reads where .idx existed."""
    indexed = [e for e in entries if e.get("idx_exists")]
    print("\n━━━ Symbol Index + Section-only Loading ━━━")
    if not indexed:
        print("  No indexed files read yet — accumulate more sessions first.")
        return 0

    hits = [e for e in indexed if e.get("offset") is not None]
    misses = [e for e in indexed if e.get("offset") is None]
    compliance = len(hits) / len(indexed) * 100

    by_file: dict[str, list[dict]] = defaultdict(list)
    for e in misses:
        by_file[e["rel"]].append(e)

    total_shadow = 0
    shadow_by_file = {}
    for rel, reads in by_file.items():
        s = reads[0]
        file_chars = s.get("file_chars", 0)
        sections = max(s.get("idx_sections", 1), 1)
        avg_section_chars = file_chars / sections
        per_read = _tokens(file_chars) - _tokens(int(avg_section_chars))
        total = per_read * len(reads)
        total_shadow += total
        shadow_by_file[rel] = (s.get("file_lines", 0), sections, per_read, len(reads), total)

    print(f"  Reads: {len(hits)} targeted  {len(misses)} full-file  ({compliance:.0f}% compliance)")
    print(f"  Estimated shadow cost: ~{total_shadow:,} tokens")
    if shadow_by_file:
        print("  Offenders:")
        for rel, (lines, secs, per_read, count, total) in sorted(
            shadow_by_file.items(), key=lambda x: -x[1][4]
        )[:8]:
            print(f"    {rel:<48} {lines:>4}L  {secs:>2} sections  ×{count}  ~{total:,} tokens")
    return total_shadow


def _report_indexing_gap(entries: list[dict]) -> int:
    """Files ≥50 lines with no .idx read in full — indexing opportunity."""
    gaps = [
        e for e in entries
        if not e.get("idx_exists")
        and e.get("file_lines", 0) >= 50
        and e.get("offset") is None
    ]
    print("\n━━━ Indexing Gap (≥50 lines, no .idx) ━━━")
    if not gaps:
        print("  None — all large files are indexed.")
        return 0

    by_file: dict[str, list[dict]] = defaultdict(list)
    for e in gaps:
        by_file[e["rel"]].append(e)

    total_est = 0
    for rel, reads in sorted(by_file.items(), key=lambda x: -x[1][0].get("file_lines", 0))[:8]:
        s = reads[0]
        est = _tokens(s.get("file_chars", 0)) * len(reads)
        total_est += est
        print(
            f"    {rel:<48} {s.get('file_lines',0):>4}L  "
            f"×{len(reads)}  ~{est:,} tokens  → add to pre-spawn reads"
        )
    return total_est


def _report_lazy_decomposition(project_root: Path) -> int:
    """Lazy decomposition: slim stubs vs eager full definitions."""
    tasks_path = project_root / "tasks.json"
    print("\n━━━ Lazy Decomposition ━━━")
    if not tasks_path.exists():
        print("  tasks.json not found.")
        return 0
    try:
        data = json.loads(tasks_path.read_text())
    except json.JSONDecodeError:
        print("  tasks.json parse error.")
        return 0

    tasks = data.get("tasks", [])
    slim = [t for t in tasks if set(t.keys()) <= {"task_id", "status"}]
    full = [t for t in tasks if len(t.keys()) > 2]

    full_tokens = sum(_tokens(len(json.dumps(t))) for t in full)
    slim_tokens = sum(_tokens(len(json.dumps(t))) for t in slim)
    eager_est = full_tokens + len(slim) * (_tokens(len(json.dumps(full[0]))) if full else 1500)

    print(f"  Tasks: {len(full)} full definitions, {len(slim)} slim stubs")
    print(f"  Current tasks.json cost per load: ~{full_tokens + slim_tokens:,} tokens")
    print(f"  Eager alternative (all full defs): ~{eager_est:,} tokens")
    print(f"  Savings already realized:          ~{eager_est - full_tokens - slim_tokens:,} tokens  ✓")
    return eager_est - full_tokens - slim_tokens


def _report_no_reread(entries: list[dict], project_root: Path) -> int:
    """No-re-read rule: files in task reads lists that were read in full anyway."""
    tasks_path = project_root / "tasks.json"
    print("\n━━━ No-re-read Rule ━━━")
    if not tasks_path.exists():
        print("  tasks.json not found.")
        return 0
    try:
        data = json.loads(tasks_path.read_text())
    except json.JSONDecodeError:
        print("  tasks.json parse error.")
        return 0

    reads_files: set[str] = set()
    for t in data.get("tasks", []):
        for r in t.get("reads", []):
            reads_files.add(r.split("#")[0])

    violations = [
        e for e in entries
        if e.get("rel") in reads_files and e.get("offset") is None
    ]
    if not violations:
        print("  No violations detected — reads list files not re-read in full.  ✓")
        return 0

    by_file: dict[str, list[dict]] = defaultdict(list)
    for e in violations:
        by_file[e["rel"]].append(e)

    total_shadow = sum(
        _tokens(reads[0].get("file_chars", 0)) * len(reads)
        for reads in by_file.values()
    )
    print(f"  Violations: {len(violations)} reads of pre-embedded files")
    print(f"  Estimated shadow cost: ~{total_shadow:,} tokens")
    for rel, reads in sorted(by_file.items(), key=lambda x: -len(x[1])):
        s = reads[0]
        print(f"    {rel:<48} {s.get('file_lines',0):>4}L  ×{len(reads)}  ~{_tokens(s.get('file_chars',0)) * len(reads):,} tokens")
    return total_shadow


def _report_state_docs(project_root: Path) -> int:
    """Compact state documents: token cost of living state files per load."""
    docs = [
        ("design_status.md", "oracle startup"),
        ("execution_plan.md", "orchestrator startup"),
        ("architecture.md", "worker reads (section-only target)"),
    ]
    print("\n━━━ Compact State Documents ━━━")
    total_tok = 0
    for name, note in docs:
        path = project_root / name
        if not path.exists():
            continue
        content = path.read_text()
        lines = len(content.splitlines())
        tok = _tokens(len(content))
        total_tok += tok
        print(f"  {name:<25} {lines:>4} lines  ~{tok:>5,} tokens/load  ({note})")
    return total_tok


def _report_verbosity_compliance(project_root: Path) -> int:
    """Output verbosity control compliance vs 150-token target."""
    log_path = project_root / ".agentflow" / "verbosity_log.jsonl"
    print("\n━━━ Output Verbosity Control ━━━")
    if not log_path.exists():
        print("  No verbosity logs recorded yet.")
        return 0
    entries = []
    for line in log_path.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not entries:
        print("  No verbosity logs recorded yet.")
        return 0
    by_type = defaultdict(list)
    for e in entries:
        st = e.get("session_type", "unknown")
        tokens = e.get("output_tokens", 0)
        by_type[st].append(tokens)
    for st, tokens in sorted(by_type.items()):
        n = len(tokens)
        mean_tokens = sum(tokens) / n if n else 0
        sorted_tokens = sorted(tokens)
        p90_idx = int(len(sorted_tokens) * 0.9)
        p90_tokens = sorted_tokens[p90_idx] if sorted_tokens else 0
        print(f"  {st:<15} mean: {mean_tokens:>5.1f} tokens, p90: {p90_tokens:>5.1f} tokens  ({n} turns, target ≤ 150)")
    return sum(max(0, 600 - e.get("output_tokens", 0)) for e in entries)


def main() -> None:
    project_root = Path.cwd()
    log_path = project_root / ".agentflow" / "shadow_reads.jsonl"
    entries = _load_log(log_path)

    print("AgentFlow Shadow Cost Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Read log:  {len(entries)} calls recorded")

    total = _report_targeted_reads(entries)
    total += _report_no_reread(entries, project_root)
    _report_indexing_gap(entries)
    _report_lazy_decomposition(project_root)
    _report_state_docs(project_root)
    _report_verbosity_compliance(project_root)

    print(f"\nTotal measurable shadow cost: ~{total:,} tokens")


if __name__ == "__main__":
    main()

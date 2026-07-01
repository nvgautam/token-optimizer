#!/usr/bin/env python3
"""Shadow cost analyzer: measures token waste from unimplemented optimizations."""

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
        except Exception:
            pass
    return entries


def _load_tasks(project_root: Path) -> list[dict]:
    path = project_root / "tasks.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("tasks", [])
    except Exception:
        return []


def get_bucketed_stats(
    project_root: Path,
    entries: list[dict],
    reads_files: set[str],
    mode: str = "aggregate",
) -> dict[str, int]:
    res = {"no-reread": 0, "targeted-reads": 0, "indexing-gap": 0, "state-docs": 0}
    sd_names = {"architecture.md", "design_status.md", "execution_plan.md"}
    for e in entries:
        rel = e.get("rel", "")
        off_none = e.get("offset") is None
        idx_ex = e.get("idx_exists")
        is_no_reread = rel in reads_files and off_none
        is_targeted = bool(idx_ex) and off_none
        fl = e.get("file_lines", 0)
        is_gap = not idx_ex and fl >= 50 and off_none and rel not in sd_names
        is_state_doc = rel in sd_names
        file_chars = e.get("file_chars", 0)
        t_val = _tokens(file_chars)
        t_targeted = t_val - _tokens(int(file_chars / max(e.get("idx_sections", 1), 1)))

        matched = False
        if is_no_reread:
            res["no-reread"] += t_val
            matched = True
        if is_targeted and (not matched or mode != "aggregate"):
            res["targeted-reads"] += t_targeted
            matched = True
        if is_gap and (not matched or mode != "aggregate"):
            res["indexing-gap"] += t_val
            matched = True
        if is_state_doc and (not matched or mode != "aggregate"):
            res["state-docs"] += t_val
    return res


def _report_targeted_reads(entries: list[dict]) -> int:
    indexed = [e for e in entries if e.get("idx_exists")]
    print("\n━━━ Symbol Index + Section-only Loading ━━━")
    if not indexed:
        print("  No indexed files read yet — accumulate more sessions first.")
        return 0

    hits = [e for e in indexed if e.get("offset") is not None]
    misses = [e for e in indexed if e.get("offset") is None]
    by_file = defaultdict(list)
    for e in misses:
        by_file[e["rel"]].append(e)

    total_shadow = 0
    shadow_by_file = {}
    for rel, reads in by_file.items():
        s = reads[0]
        file_chars = s.get("file_chars", 0)
        sections = max(s.get("idx_sections", 1), 1)
        per_read = _tokens(file_chars) - _tokens(int(file_chars / sections))
        total = per_read * len(reads)
        total_shadow += total
        fl = s.get("file_lines", 0)
        shadow_by_file[rel] = (fl, sections, per_read, len(reads), total)

    c = (len(hits) / len(indexed) * 100) if indexed else 0
    print(f"  Reads: {len(hits)} targeted  {len(misses)} full ({c:.0f}% compliance)")
    print(f"  Estimated shadow cost: ~{total_shadow:,} tokens")
    if shadow_by_file:
        print("  Offenders:")
        for rel, (lines, secs, per_read, count, total) in sorted(
            shadow_by_file.items(), key=lambda x: -x[1][4]
        )[:8]:
            t = f"    {rel:<40} {lines:>4}L {secs:>2}sec x{count} ~{total:,}T"
            print(t)
    return total_shadow


def _is_gap(e: dict) -> bool:
    lines = e.get("file_lines", 0)
    return not e.get("idx_exists") and lines >= 50 and e.get("offset") is None


def _report_indexing_gap(entries: list[dict]) -> int:
    gaps = [e for e in entries if _is_gap(e)]
    print("\n━━━ Indexing Gap (≥50 lines, no .idx) ━━━")
    if not gaps:
        print("  None — all large files are indexed.")
        return 0
    by_file = defaultdict(list)
    for e in gaps:
        by_file[e["rel"]].append(e)
    total_est = 0
    for rel, reads in sorted(
        by_file.items(), key=lambda x: -x[1][0].get("file_lines", 0)
    )[:8]:
        est = _tokens(reads[0].get("file_chars", 0)) * len(reads)
        total_est += est
        fl = reads[0].get("file_lines", 0)
        print(f"    {rel:<40} {fl:>4}L  x{len(reads)}  ~{est:,}T -> pre-spawn")
    return total_est


def _report_lazy_decomposition(project_root: Path) -> int:
    print("\n━━━ Lazy Decomposition ━━━")
    tasks = _load_tasks(project_root)
    if not tasks:
        return 0
    slim = [t for t in tasks if set(t.keys()) <= {"task_id", "status"}]
    full = [t for t in tasks if len(t.keys()) > 2]
    f_tok = sum(_tokens(len(json.dumps(t))) for t in full)
    s_tok = sum(_tokens(len(json.dumps(t))) for t in slim)
    eager = f_tok + len(slim) * (_tokens(len(json.dumps(full[0]))) if full else 1500)
    print(f"  Tasks: {len(full)} full, {len(slim)} slim")
    print(f"  Current cost: ~{f_tok + s_tok:,} | Eager: ~{eager:,} tokens")
    diff = eager - f_tok - s_tok
    print(f"  Savings realized: ~{diff:,} tokens  ✓")
    return diff


def _report_no_reread(entries: list[dict], project_root: Path) -> int:
    print("\n━━━ No-re-read Rule ━━━")
    tasks = _load_tasks(project_root)
    if not tasks:
        return 0

    reads_files = set()
    for t in tasks:
        for r in t.get("reads", []):
            reads_files.add(r.split("#")[0])

    violations = [
        e for e in entries if e.get("rel") in reads_files and e.get("offset") is None
    ]
    if not violations:
        print("  No violations detected.  ✓")
        return 0

    by_file = defaultdict(list)
    for e in violations:
        by_file[e["rel"]].append(e)

    total_shadow = sum(
        _tokens(reads[0].get("file_chars", 0)) * len(reads)
        for reads in by_file.values()
    )
    print(f"  Violations: {len(violations)} reads of pre-embedded files")
    print(f"  Estimated shadow cost: ~{total_shadow:,} tokens")
    for rel, reads in sorted(by_file.items(), key=lambda x: -len(x[1])):
        c_tok = _tokens(reads[0].get("file_chars", 0)) * len(reads)
        fl = reads[0].get("file_lines", 0)
        print(f"    {rel:<40} {fl:>4}L x{len(reads)} ~{c_tok:,}T")
    return total_shadow


def _report_state_docs(project_root: Path) -> int:
    print("\n━━━ Compact State Documents ━━━")
    total_tok = 0
    for name, note in [
        ("design_status.md", "oracle"),
        ("execution_plan.md", "orchestrator"),
        ("architecture.md", "worker"),
    ]:
        path = project_root / name
        if path.exists():
            content = path.read_text()
            tok = _tokens(len(content))
            total_tok += tok
            lns = len(content.splitlines())
            print(f"  {name:<20} {lns:>4}L ~{tok:>5}T ({note})")
    return total_tok


def _report_verbosity_compliance(project_root: Path) -> int:
    log_path = project_root / ".agentflow" / "verbosity_log.jsonl"
    print("\n━━━ Output Verbosity Control ━━━")
    entries = []
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    if not entries:
        print("  No verbosity logs recorded yet.")
        return 0
    by_type = defaultdict(list)
    for e in entries:
        by_type[e.get("session_type", "unknown")].append(e.get("output_tokens", 0))
    for st, tokens in sorted(by_type.items()):
        n = len(tokens)
        mean_tokens = sum(tokens) / n if n else 0
        sorted_tokens = sorted(tokens)
        p90_tokens = sorted_tokens[int(n * 0.9)] if sorted_tokens else 0
        m, p = mean_tokens, p90_tokens
        print(f"  {st:<15} mean: {m:.1f}, p90: {p:.1f} ({n} turns, target <= 150)")
    return sum(max(0, 600 - e.get("output_tokens", 0)) for e in entries)


def main() -> None:
    r = Path.cwd()
    ents = _load_log(r / ".agentflow" / "shadow_reads.jsonl")
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"Shadow Report | {dt} | {len(ents)} calls")
    t = _report_targeted_reads(ents) + _report_no_reread(ents, r)
    _report_indexing_gap(ents)
    _report_lazy_decomposition(r)
    _report_state_docs(r)
    _report_verbosity_compliance(r)
    print(f"\nTotal measurable shadow cost: ~{t:,} tokens")


if __name__ == "__main__":
    main()

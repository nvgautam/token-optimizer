#!/usr/bin/env python3
"""PreToolUse hook: block full reads on files that have a section map."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("AbsolutePath")
        or tool_input.get("TargetFile")
    )
    if not file_path:
        sys.exit(0)

    cwd = os.getcwd()
    try:
        rel = str(Path(file_path).relative_to(cwd))
    except ValueError:
        sys.exit(0)

    cwd_hash = hashlib.sha256(cwd.encode()).hexdigest()
    map_path = (
        Path.home() / ".agentflow" / "cache" / cwd_hash / "index" / f"{rel}.idx"
    )

    offset = tool_input.get("offset")
    limit = tool_input.get("limit")

    start_line = tool_input.get("StartLine")
    end_line = tool_input.get("EndLine")

    if start_line is not None and end_line is not None:
        try:
            offset = int(start_line)
            limit = int(end_line) - offset + 1
        except (ValueError, TypeError) as e:
            print(json.dumps({"hook": "read_check.py", "event": "parse_line_range_error", "error": str(e), "start_line": str(start_line), "end_line": str(end_line), "ts": time.time()}), file=sys.stderr)
    elif start_line is not None:
        try:
            offset = int(start_line)
        except (ValueError, TypeError) as e:
            print(json.dumps({"hook": "read_check.py", "event": "parse_start_line_error", "error": str(e), "start_line": str(start_line), "ts": time.time()}), file=sys.stderr)

    if offset is not None and limit is not None:
        if not map_path.exists():
            sys.exit(0)
        sections = map_path.read_text().strip()
        if not sections:
            sys.exit(0)

        # Count total lines in file (stdlib only)
        try:
            p = Path(file_path)
            if not p.is_absolute():
                p = Path(cwd) / p
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                total_lines = sum(1 for _ in f)
        except Exception as e:
            print(json.dumps({"hook": "read_check.py", "event": "count_file_lines_error", "error": str(e), "file_path": file_path, "ts": time.time()}), file=sys.stderr)
            sys.exit(0)

        # If file < 50 lines → skip check
        if total_lines < 50:
            sys.exit(0)

        # Compute coverage = limit / (total_lines - offset)
        try:
            offset_val = int(offset)
            limit_val = int(limit)
        except (ValueError, TypeError):
            sys.exit(0)

        denom = total_lines - offset_val
        coverage = limit_val / denom if denom > 0 else 0.0

        # Threshold configurable via AGENTFLOW_READ_COVERAGE_THRESHOLD env var
        threshold_str = os.environ.get("AGENTFLOW_READ_COVERAGE_THRESHOLD")
        try:
            threshold = float(threshold_str) if threshold_str is not None else 0.60
        except ValueError:
            threshold = 0.60

        # If coverage > threshold AND idx exists → exit 1
        if coverage > threshold:
            pct = int(round(coverage * 100))
            print(
                f"Large-range read ({limit_val}/{total_lines} lines, {pct}%) — use idx to target specific sections",
                file=sys.stderr,
            )
            sys.exit(1)

        sys.exit(0)

    elif offset is not None:
        sys.exit(0)

    if not map_path.exists():
        sys.exit(0)

    sections = map_path.read_text().strip()
    if not sections:
        sys.exit(0)

    print(f"Blocked read of {rel}: use Read(offset=N, limit=M)", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()

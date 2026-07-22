import json
import os
from pathlib import Path

def get_section(file_path: Path, start: int, end: int) -> str:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    # 1-indexed lines
    selected = lines[start-1:end]
    return "\n".join(selected)

def main():
    root = Path.cwd()
    
    # 1. Load worker guides
    system_prompt = (root / "commands" / "claude" / "worker" / "system.md").read_text("utf-8")
    context_bundle = (root / "commands" / "claude" / "worker" / "context_bundle.md").read_text("utf-8")
    testing_guide = (root / "commands" / "claude" / "worker" / "testing_guide.md").read_text("utf-8")
    
    # 2. Build the task brief for T-311
    task_brief = """
# TASK BRIEF
Task ID: T-311
Title: Session-scoped log observability: session header + SID on every log line + logs CLI subcommand + ops skill

Goal: Friendly supportability: emit a structured session-start header record into every log file (`sid`, `session_type` ∈ {oracle, orchestrator, worker, reviewer}, `task_ids` being worked on, `ts`). Add `"sid"` to every subsequent JSONL entry. Add `agentflow logs --session <SID>` CLI command so friendlies can export their session logs in one command and paste for remote triage. `commands/claude/debug.md` is customer-facing and must NOT reference AgentFlow-internal log paths or SID mechanics — keep it clean. AgentFlow-internal log triage lives in a new internal-only ops skill (`commands/claude/ops.md`) NOT bundled into customer distribution.

Owned Files:
- `agentflow/hooks/post_tool_use_agent.py`
- `agentflow/shell/pty_shell.py`
- `agentflow/cli.py`
- `commands/claude/ops.md`
- `tests/test_log_sid_injection.py`

Test Scenarios:
- Session-start header record emitted as first entry per SID with correct session_type and task_ids
- Every subsequent hook_drain_debug.jsonl and pty_audit.jsonl entry has matching `sid`
- Two interleaved sessions: grep by SID A returns only A's entries including its header
- `agentflow logs --session <SID>` outputs complete picture of one session to stdout

Acceptance Criteria:
All unit tests in tests/test_log_sid_injection.py pass and assert the session-start header and SID are present in all log entries, and validation of logs subcommand output.
"""

    # 3. Read and format dependencies based on their idx files
    dependencies_content = "\n# READ-ONLY DEPENDENCY SECTIONS\n"
    
    # post_tool_use_agent.py sections
    f_path = root / "agentflow" / "hooks" / "post_tool_use_agent.py"
    dependencies_content += "\n## File: agentflow/hooks/post_tool_use_agent.py\n"
    for name, start, end in [
        ("_find_workspace_root", 23, 31),
        ("_log", 34, 39),
        ("_mark_task_complete", 42, 75),
        ("_run_cleanup", 78, 83),
        ("main", 86, 198)
    ]:
        content = get_section(f_path, start, end)
        dependencies_content += f"### {name} (lines {start}-{end})\n```python\n{content}\n```\n\n"

    # pty_shell.py sections
    f_path = root / "agentflow" / "shell" / "pty_shell.py"
    dependencies_content += "\n## File: agentflow/shell/pty_shell.py\n"
    content = get_section(f_path, 21, 135)
    dependencies_content += f"### ProxyShell (lines 21-135)\n```python\n{content}\n```\n\n"

    # cli.py sections
    f_path = root / "agentflow" / "cli.py"
    dependencies_content += "\n## File: agentflow/cli.py\n"
    for name, start, end in [
        ("build_parser", 70, 139),
        ("main", 142, 178)
    ]:
        content = get_section(f_path, start, end)
        dependencies_content += f"### {name} (lines {start}-{end})\n```python\n{content}\n```\n\n"


    # 4. Assemble everything
    full_prompt = f"""{system_prompt}

---

{context_bundle}

---

{testing_guide}

---

{task_brief}

---

{dependencies_content}

---

End your final message with "TOKENS: input=N output=N — nothing after that line."
"""
    
    out_path = root / ".agentflow" / "worker_prompt_T-311.md"
    out_path.write_text(full_prompt, encoding="utf-8")
    print(f"Wrote worker prompt to {out_path}, size = {len(full_prompt)} chars")

if __name__ == "__main__":
    main()

# AgentFlow

Provider-agnostic multi-agent project management: skills for Claude and Gemini + PTY overlay shell that manages context lifecycle transparently. Reduces token consumption by cycling agent context at task boundaries and enabling targeted file reads via a local symbol index.

## Commands
- Test:  `pytest tests/` (for metadata/task-only changes, run targeted tests like `pytest tests/test_cleanup_tasks.py`)
- Lint:  `ruff check .`
- Build: `python -m build`

## Structure
```
agentflow/shell/                → PTY overlay shell — token counting, threshold, handoff inject, session restart (zero LLM calls)
agentflow/hooks/                → PostToolUse/UserPromptSubmit hooks: read_check, idx_reminder, verbosity_reminder, write_indexer, size_check
commands/                       → Provider skill files: Claude (claude/) and Gemini (gemini/skills/) — this IS the oracle/worker/reviewer/orchestrator logic
agentflow/config/                → Layered config: threshold settings, model config (Pydantic v2)
agentflow/indexer/              → Symbol index — ~/.agentflow/cache/<project-hash>/index/ (standalone CLI tool)
agentflow/shadow/               → Savings-across-strategies analyzer (targeted reads, no-reread, verbosity, headroom) — feeds `agentflow report`
```

`agentflow/oracle/`, `orchestrator/`, `worker/`, `reviewer/`, `tools/` (Python packages, not the skill files above) are a deferred/dead headless-automation-layer prototype — never wired into `cli.py` or any skill. See architecture.md's "Deferred (v2)" section. Do not extend or document as live.

## State documents (living — updated continuously, not written once)
```
design_status.md     → Oracle state: RESOLVED / UNRESOLVED / DEFERRED design decisions
                       Oracle reads this on startup (not architecture.md)
architecture.md      → Design reference: module boundaries, PTY design, config schema, etc.
                       Workers read anchored sections; oracle does not read this at startup
execution_plan.md    → Milestone state: milestone structure + Milestone 1 tasks (full);
                       Orchestrator extends with tasks for each subsequent milestone on prior completion
tasks.json           → Task state: {task_id, status}, status ∈ {pending, complete};
                       execution_plan.md carries MERGED per task once the skill confirms the merge
tasks.db             → Migration artifact ONLY — NOT the active store; tasks.json is authoritative. Ignore .agentflow/tasks.db-shm/.db-wal artifacts in git status.
```

## Integrations
```
PTY shell: none — stdlib-only, no direct API calls
Skills execute via Claude Code / Gemini CLI
```

## Constraints
- Compliance: None
- No secrets in code or config — env vars only, never logged
- No implementation file > 250 lines; tests ≤ 350; prompts ≤ 150; stubs ≤ 100
- No two modules share ownership of the same file
- PTY shell: zero LLM calls, stdlib-only, fully deterministic
- Symbol index: `~/.agentflow/cache/<project-hash>/index/` — not committed, not visible in project
- Pydantic v2 for all structured inputs and config validation
- Human PR approval is an enforced gate — the skill never marks a task `complete`/`MERGED` before the human merges on GitHub
- Every operation must be idempotent — safe to run twice with the same result
- Brownfield: index generation v1; file refactoring deferred to v2
- Codex provider: v2
- Tier/licensing model: deferred
- Naming/branding: deferred

## Reading protocol

Before reading any file, check for a `.idx` symbol index:

```bash
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
IDX=~/.agentflow/cache/$HASH/index/<relative-path>.idx
```

If the `.idx` exists:
- Grep for the symbol/section you need: `grep "^<name>:" "$IDX"`
- Result is `name:start-end` — call `Read(file, offset=start, limit=end-start+1)`

If the `.idx` is absent: the file is < 50 lines or not yet indexed — read the full file without `offset`/`limit`. No special handling needed.

## Tech stack
Python 3.11+, Pydantic v2, tiktoken
PTY shell deps: stdlib only (pty, subprocess, signal, time, re, pathlib, hashlib)

## Deployment
Compiled binary for PTY shell (Nuitka) + pip-installable package (runtime modules)

## Post-merge checklist
After merging any branch into main, verify these patterns survive — they are overwritten silently on conflicts:

1. **Oracle gate (startup.md + oracle.md):** must use `awk -F'|' '{gsub(/^[[:space:]]+|[[:space:]]+$/,"",$2); if($2=="UNRESOLVED")c++}END{print c+0}'` — NOT `grep -c '| UNRESOLVED |'` (grep matches description text, produces false positives).
2. **Skill file sizes:** `wc -l commands/claude/oracle.md commands/claude/orchestrate.md` — each must be ≤ 150 lines per constraint.
3. **Config schema:** `agentflow/config/models.py` — verify `oracle_threshold_tokens` field present after merging config branches.

Quick verify: `grep -n 'UNRESOLVED' commands/claude/orchestrator/startup.md commands/claude/oracle.md` — both lines must contain `awk -F'|'`, not `grep`.

## Reference
- Design decisions:  design_status.md
- Full architecture: architecture.md
- Milestone plan:    execution_plan.md
- Task status:       tasks.json
- Troubleshooting:   commands/claude/ops.md

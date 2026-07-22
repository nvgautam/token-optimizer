# AgentFlow — Project Guidelines & Rules

Project guide for Antigravity (AGY) sessions in the Token Optimizer / AgentFlow workspace.

## Commands
- Test:  `pytest tests/` (for metadata/task-only changes, run targeted tests like `pytest tests/test_cleanup_tasks.py`)
- Lint:  `ruff check .`
- Build: `python -m build`

## Structure
```
agentflow/shell/                → PTY overlay shell — token counting, threshold, handoff inject, session restart (zero LLM calls)
agentflow/hooks/                → PostToolUse/UserPromptSubmit hooks: read_check, idx_reminder, verbosity_reminder, write_indexer, size_check
commands/                       → Provider skill files: Claude (claude/) and Gemini (gemini/skills/) — this IS the oracle/worker/reviewer/orchestrator logic
agentflow/config/               → Layered config: threshold settings, model config (Pydantic v2)
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
execution_plan.md    → Milestone state + round → task_id mapping (Master Round Table);
                       USE THIS for next-round selection and task-ID lookup, not tasks.db or tasks.json
tasks.json           → Task state: individual task lifecycle PENDING → MERGED; use Python one-liner to extract pending entries
tasks.db             → RETIRED migration artifact — DO NOT READ; execution_plan.md owns round data, tasks.json owns task status
```

## Integrations
```
PTY shell: none — stdlib-only, no direct API calls
Skills execute via Claude Code / Gemini CLI (agy)
```

## Constraints
- tasks.db is a RETIRED migration artifact — never read or query it; use execution_plan.md (Master Round Table) for round→task mapping
- Compliance: None
- No secrets in code or config — env vars only, never logged
- No implementation file > 250 lines; tests ≤ 350; prompts ≤ 150; stubs ≤ 100
- No two modules share ownership of the same file
- PTY shell: zero LLM calls, stdlib-only, fully deterministic
- Symbol index: `~/.agentflow/cache/<project-hash>/index/` — not committed, not visible in project
- Pydantic v2 for all structured inputs and config validation
- Human PR approval is an enforced gate (HUMAN_APPROVED state), not advisory
- Every operation must be idempotent — safe to run twice with the same result
- Brownfield: index generation v1; file refactoring deferred to v2
- Codex provider: v2
- Tier/licensing model: deferred
- Naming/branding: deferred

## Tech stack
Python 3.11+, Pydantic v2, tiktoken
PTY shell deps: stdlib only (pty, subprocess, signal, time, re, pathlib, hashlib)

## Deployment
Compiled binary for PTY shell (Nuitka) + pip-installable package (runtime modules)

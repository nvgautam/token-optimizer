# AgentFlow

Provider-agnostic multi-agent project management: skills for Claude and Gemini + PTY overlay shell that manages context lifecycle transparently. Reduces token consumption by cycling agent context at task boundaries and enabling targeted file reads via a local symbol index.

## Commands
- Test:  `pytest tests/`
- Lint:  `ruff check .`
- Build: `python -m build`

## Structure
```
agentflow/shell/        → PTY overlay shell — token tracking, threshold, session restart (zero LLM calls)
agentflow/skills/       → Provider skill files — Claude (.md), Gemini (SKILL.md + scripts)
agentflow/oracle/       → Design sparring — market-aware multi-persona checklist, architecture.md + CLAUDE.md
agentflow/orchestrator/ → Execution planning — execution_plan.md, tasks.json, milestone state machine
agentflow/worker/       → Headless agent runner, context builder, write_file tool with index hook
agentflow/indexer/      → Symbol index — ~/.agentflow/cache/<project-hash>/index/ — never in project tree
agentflow/reviewer/     → Code and security review agents
agentflow/tools/        → Git worktrees, GitHub API, test runner, file validator
agentflow/telemetry/    → Token tracking, ledger, structured logging
agentflow/config/       → Layered config: env → project → user → defaults (Pydantic v2)
```

## State documents (living — updated continuously, not written once)
```
architecture.md      → Oracle state: RESOLVED / UNRESOLVED / DEFERRED design items
execution_plan.md    → Orchestrator state: milestones mapped to tasks, completion tracking
tasks.json           → Task state: individual task lifecycle PENDING → MERGED
```

## Integrations
```
GitHub API      → tools/github.py          credentials: GITHUB_TOKEN env var — never logged
Anthropic API   → worker/agent_runner.py   credentials: ANTHROPIC_API_KEY env var — never logged
Gemini API      → worker/agent_runner.py   credentials: GEMINI_API_KEY env var — never logged
```

## Constraints
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
Python 3.11+, Pydantic v2, httpx, tiktoken, watchdog
PTY shell deps: stdlib only (pty, subprocess, signal, time, re, pathlib, hashlib)

## Deployment
Compiled binary for PTY shell (Nuitka) + pip-installable package (runtime modules)

## Reference
- Full architecture: architecture.md
- Task status:       tasks.json

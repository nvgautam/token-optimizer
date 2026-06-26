# AgentFlow

Provider-agnostic multi-agent project management: skills for Claude and Gemini + PTY overlay shell that manages context lifecycle transparently. Reduces token consumption by cycling agent context at task boundaries and enabling targeted file reads via a local symbol index.

## Commands
- Test:  `pytest tests/`
- Lint:  `ruff check .`
- Build: `python -m build`

## Structure
```
agentflow/shell/                → PTY overlay shell — token counting, threshold, handoff inject, session restart (zero LLM calls)
agentflow/skills/               → Provider skill files — Claude (.md), Gemini (SKILL.md + scripts)
agentflow/oracle/prompts/       → Oracle prompt files (system, market, checklist, generation)
agentflow/worker/prompts/       → Worker prompt files (system, context_bundle, testing_guide)
agentflow/worker/context_builder.py → Assembles minimal context bundle per task; writes context_bundle.md to disk
agentflow/reviewer/prompts/     → Reviewer prompt files (code_review, security_review, test_review)
agentflow/orchestrator/prompts/ → Orchestrator prompt files (system, planning)
agentflow/config/               → Layered config: threshold settings, model config (Pydantic v2)
agentflow/indexer/              → Symbol index — ~/.agentflow/cache/<project-hash>/index/ (standalone CLI tool)
```

## State documents (living — updated continuously, not written once)
```
architecture.md      → Oracle state: RESOLVED / UNRESOLVED / DEFERRED design items
execution_plan.md    → Orchestrator state: milestones mapped to tasks, completion tracking
tasks.json           → Task state: individual task lifecycle PENDING → MERGED
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

## Reference
- Full architecture: architecture.md
- Task status:       tasks.json

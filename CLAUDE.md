# CLAUDE.md — AgentFlow / Token Optimizer

A standalone tool for multi-agent session management and token optimization. Developed here first; validated results applied back to the OCI Assistant project and eventually productized.

---

## What this project is

A system that reduces Claude/Gemini token consumption by:
1. **Session cycling** — resetting agent context at task boundaries rather than letting it balloon
2. **Token measurement** — tracking real vs shadow (hypothetical single-session) token usage
3. **PTY orchestration** (Phase 3) — automating session restarts transparently via a terminal wrapper

See `VISION.md` for the full product vision and `AGENT_ORCHESTRATOR_PLAN.md` for the PTY architecture.

---

## Project layout

```
token-optimizer/
├── agentflow.py              # Core tool: session logger, shadow model, batch_decision, ctx-watch
├── agentflow_ledger.json     # This project's session data (gitignored: add to .gitignore if sensitive)
├── scripts/                  # Token scan, toggle, split-file helpers (Phase 2)
├── test/                     # Tests
├── TASK_BOARD.md             # Authoritative task list
├── VISION.md                 # Product vision (ported from OCI project_manager_token_optimizer.md)
└── AGENT_ORCHESTRATOR_PLAN.md  # PTY orchestrator architecture
```

---

## Key commands

```bash
python agentflow.py handoff          # Record session token usage at session end
python agentflow.py report           # Show cumulative savings (shadow/real ratio)
python agentflow.py batch-check "task subject"   # Should next task batch or start fresh?
python agentflow.py classify "task subject"      # mechanical or exploratory?
```

---

## Relationship to OCI Assistant

- `agentflow.py` is installed in `/Users/gautam/code/oci/oci-assistant/` as a copy.
- When making changes here, manually sync to OCI after validating.
- OCI-specific optimization tasks (CLAUDE.md hygiene, task board verbosity) stay in OCI's TASK_BOARD.md.
- The source of truth for agentflow.py development is this repo.

---

## Validation target

**Run `python agentflow.py report` after each session.** The success criterion is shadow/real ≥ 3× across 10+ sessions. Track in ledger. If ratio falls short, investigate task granularity (tasks spanning multiple sessions should be split).

---

## Development conventions

- Keep `agentflow.py` self-contained — one file, no external deps beyond stdlib.
- Test changes against the JSONL reader before committing (needs a live `~/.claude/projects/` entry).
- Do not add LLM calls to agentflow.py core — it must work offline.
- PTY orchestrator (Phase 3) is a separate module; do not entangle with the core logger.

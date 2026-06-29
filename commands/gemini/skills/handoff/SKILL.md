---
name: handoff
description: Flush current session state to the living document, emit PTY signal, and record telemetry.
---

# /handoff — Session State Flush

Flush session state to living document, emit PTY signal, record telemetry.

## Proactive handoff signals

Skills emit `HANDOFF RECOMMENDED: <reason>` at natural stopping points:
- Oracle: after each batch resolves (functional/NFR/integrations/security/quality gates)
- Orchestrator: when task reaches PR_OPEN; after each merge

Format: `HANDOFF RECOMMENDED: <reason>` — PTY and manual mode use as context boundary signal.

## On invocation

### Step 1 — Detect session type

- Read `design_status.md` — `| UNRESOLVED |` present → **oracle session**
- Read `execution_plan.md` — `Status: IN_PROGRESS` present → **orchestrator session**
- Otherwise → **unknown**

### Step 2 — Flush state

Compact format: tables and bullets only; no prose.

| Session type | Action |
|---|---|
| oracle | Update `design_status.md` rows for all items resolved/changed |
| orchestrator | Update `execution_plan.md` — mark tasks completed/merged/in-progress |
| unknown | Skip |

**design_status.md row:** `| <Item> | RESOLVED \| UNRESOLVED \| DEFERRED | <one-line decision> |`

**execution_plan.md row:** `| T-NNN | Title | Depends on | MERGED \| PENDING \| IN_PROGRESS |`

### Step 3 — Gather session data

Run in parallel:
- `git log --oneline -20`
- `git status --short`
- `git diff --stat main`
- `grep -r "ESCALATE:" .agentflow/ 2>/dev/null`
- Read `.agentflow/state.json`
- Read `tasks.json`

Use git output for state — don't infer from conversation history.

### Step 4 — Verify and prune worktrees

Run `git worktree list`. For each non-main branch:
- `git diff main...<branch> --name-only` → unmerged files?
- Unmerged → STOP; report before proceeding
- Merged → `git worktree remove --force <path>` then `git branch -d <branch>`

### Step 5 — Aggregate token ledger

Scan conversation for `TOKENS: input=N output=N`. Sum `agent_tokens_in`, `agent_tokens_out`; count `agents`. Check latest `session_complete` in `.agentflow/telemetry.jsonl` to avoid double-counting.

Append:
```json
{"event": "handoff", "timestamp": "<ISO8601>", "session_type": "oracle|orchestrator|unknown", "agent_tokens_in": N, "agent_tokens_out": N, "agents": N}
```

### Step 6 — Write handoff file

Write `.agentflow/handoff_<YYYY-MM-DD>.md`:
```markdown
---
name: handoff-<YYYY-MM-DD>
description: <one-line summary>
session_type: oracle|orchestrator|unknown
---

## Completed this session
- <deliverables>

## Key decisions
- <non-obvious choices, tradeoffs, deviations>

## Open items / next steps
- <unfinished, next steps, known issues>

## State document updated
<path flushed, or "none">
```

### Step 7 — Run ledger script

Run silently:
```bash
python /Users/gautam/code/token-optimizer/agentflow.py handoff --ledger <cwd>/agentflow_ledger.json
```

### Step 8 — Print HANDOFF_COMPLETE

Last output (PTY scans stdout for this):
```
HANDOFF_COMPLETE: .agentflow/handoff_<YYYY-MM-DD>.md
```

### Step 9 — Report to user

- Path of handoff file written
- State document updated
- Open items / next steps

`debug` argument → also report per-agent token breakdown and ledger entry written.

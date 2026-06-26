# /handoff — Session State Flush

Flush current session state to the living document, emit PTY signal, and record telemetry.

## Proactive handoff signals

Skills emit `HANDOFF RECOMMENDED: <reason>` proactively at natural stopping points — before `/handoff` is invoked:
- Oracle: emit `HANDOFF RECOMMENDED: [section] checklist items resolved` after each batch (functional/NFR/integrations/security/quality gates) resolves
- Orchestrator: emit `HANDOFF RECOMMENDED: [task_id] PR open — good stopping point before review` when a task reaches PR_OPEN state
- Orchestrator: emit `HANDOFF RECOMMENDED: [task_id] merged — good stopping point before next round` after each merge

Format: `HANDOFF RECOMMENDED: <reason>` — PTY shell (and user in manual mode) uses this to know when context is at a natural boundary.

## On invocation

### Step 1 — Detect session type

Check in order:
- Read `design_status.md` — if it contains `| UNRESOLVED |` in any row → **oracle session**
- Read `execution_plan.md` — if it contains `Status: IN_PROGRESS` → **orchestrator session**
- Otherwise → **unknown session type**

### Step 2 — Flush state to living document

**Compact format rule:** tables and bullet points only — no prose paragraphs. Target: 35-40% smaller than prose equivalent.

| Session type | Action |
|---|---|
| oracle | Update `design_status.md` — update table rows for all design items resolved or changed this session |
| orchestrator | Update `execution_plan.md` — mark tasks completed/merged/in-progress this session |
| unknown | Skip |

**design_status.md row format:**
```
| <Item> | RESOLVED \| UNRESOLVED \| DEFERRED | <one-line decision or open question or scope note> |
```

**execution_plan.md task row format:**
```
| T-NNN | Title | Depends on | MERGED | PENDING | IN_PROGRESS |
```

### Step 3 — Gather session data

Run in parallel:
- `git log --oneline -20`
- `git status --short`
- `git diff --stat main`
- `grep -r "ESCALATE:" .agentflow/ 2>/dev/null`
- Read `.agentflow/state.json` (if exists)
- Read `tasks.json` (if exists)

Use `git status` and `git diff --stat` for codebase state — do not infer from conversation history.

### Step 4 — Verify and prune worktrees

Run `git worktree list`. For each branch other than main:
- `git diff main...<branch> --name-only` → check for unmerged files
- Unmerged: STOP — report which branch has unmerged work before proceeding
- Fully merged: `git worktree remove --force <path>` then `git branch -d <branch>`

Report branches cleaned or confirm none present.

### Step 5 — Aggregate token ledger

Scan conversation for `TOKENS: input=N output=N` patterns. Sum:
- `agent_tokens_in` = sum of all agent input tokens
- `agent_tokens_out` = sum of all agent output tokens
- `agents` = count of distinct agent summaries found

Read most recent `session_complete` entry from `.agentflow/telemetry.jsonl` to avoid double-counting.

Append to `.agentflow/telemetry.jsonl`:
```json
{"event": "handoff", "timestamp": "<ISO8601>", "session_type": "oracle|orchestrator|unknown", "agent_tokens_in": N, "agent_tokens_out": N, "agents": N}
```

### Step 6 — Write handoff state

Create `.agentflow/` if missing. Write `.agentflow/handoff_<YYYY-MM-DD>.md`:

```markdown
---
name: handoff-<YYYY-MM-DD>
description: <one-line summary of what was accomplished>
session_type: oracle|orchestrator|unknown
---

## Completed this session
- <bullet list of concrete deliverables>

## Key decisions
- <non-obvious choices, trade-offs, deviations from plan>

## Open items / next steps
- <what's unfinished, what comes next, known issues>

## State document updated
<path to architecture.md or execution_plan.md flushed, or "none">
```

### Step 7 — Run ledger script

Run silently (suppress output):
```bash
python /Users/gautam/code/token-optimizer/agentflow.py handoff --ledger <cwd>/agentflow_ledger.json
```

### Step 8 — Print HANDOFF_COMPLETE

This MUST be the last output — PTY shell scans stdout for this signal:
```
HANDOFF_COMPLETE: .agentflow/handoff_<YYYY-MM-DD>.md
```

### Step 9 — Report to user

Always report:
- Path of handoff file written
- State document updated (path)
- Open items / next steps

If the argument is `debug`, also report:
- Per-agent token breakdown (input/output) and totals
- The aggregated ledger entry written

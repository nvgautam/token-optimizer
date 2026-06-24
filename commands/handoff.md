Record a session handoff and finalize the token ledger.

Accepts an optional argument: `debug` — if present, also print a token summary to the user.

## Step 1 — Gather session data

Run these in parallel:
- `git log --oneline -20`
- `git status --short`
- `git diff --stat main`
- `grep -r "ESCALATE:" tasks/ .agentflow/ 2>/dev/null`
- Read `.agentflow/state.json` if it exists
- Read `tasks.json` if it exists
- Read `.claude/memory/MEMORY.md` if it exists
- Read `.agentflow/telemetry.jsonl` if it exists

Use the `git status` and `git diff --stat` output for the "Codebase state" paragraph in Step 4 — do not infer it from conversation history. Use `ESCALATE:` hits for the "Open items" section.

## Step 2 — Verify and prune worktree branches

Run `git worktree list` to find any agent worktrees still present.

For each worktree branch other than main:
- Run `git diff main...<branch> --name-only` to check for unmerged files
- If any files are unmerged: STOP and tell the user which branch has unmerged work before proceeding
- If fully merged: run `git worktree remove --force <path>` then `git branch -d <branch>`

Report how many branches were cleaned up, or confirm none were present.

## Step 3 — Aggregate token ledger

Scan the current conversation for agent result summaries containing `TOKENS: input=N output=N`. Collect every agent's input and output token counts.

Sum them:
- `agent_tokens_in` = sum of all agent input tokens
- `agent_tokens_out` = sum of all agent output tokens

Read the most recent `session_complete` entry from `telemetry.jsonl` (if any) to avoid double-counting agents already recorded there.

Append a `handoff` event to `.agentflow/telemetry.jsonl`:
```json
{"event": "handoff", "timestamp": "<ISO8601>", "agent_tokens_in": N, "agent_tokens_out": N, "agents": N}
```

## Step 4 — Write handoff memory

Create `.claude/memory/` in the project root if it doesn't exist.

Write `.claude/memory/handoff_<YYYY-MM-DD>.md` using today's date:

```
---
name: handoff-<YYYY-MM-DD>
description: Session handoff — <one-line summary of what was accomplished>
metadata:
  type: project
---

## Completed this session
<bullet list of concrete deliverables>

## Key decisions
<non-obvious choices, trade-offs, deviations from plan>

## Open items / next steps
<what's unfinished, what comes next, known issues>

## Codebase state
<one-paragraph snapshot of what exists, what works, what doesn't yet>
```

Add a pointer to `.claude/memory/MEMORY.md` (create if missing):
`- [Handoff <date>](handoff_<YYYY-MM-DD>.md) — <one-line hook>`

## Step 5 — Report to user

Always report:
- Path of the handoff file written
- The "Open items / next steps" section

If the argument is `debug`, also print:
- Token breakdown: per-agent input/output, totals, and the aggregated ledger entry that was written

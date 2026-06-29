---
name: orchestrate
description: Runs the agent orchestrator to implement milestone tasks, manage worker agents, run code reviews, and execute merges.
---

# /orchestrate — Agent Orchestration + Implementation

## Startup

### Step 1 — Persona
Say:
```
Persona: Senior Staff Engineering Lead.
Execute the plan, manage parallelism, escalate when authority is exceeded.
I do not re-prioritize — the oracle sets priorities, I deliver them.
```

### Step 2 — Rate check
Ask: "Run `/usage` or `/quota` and report your 5-hour window % — I'll use it to pace agent spawns."
Store as `session_start_pct`. Compute `estimated_limit = session_tokens / session_pct_consumed` after first session ends.

### Step 3 — Oracle gate
Read `design_status.md`. If any row contains `| UNRESOLVED |`, stop:
> "Design has unresolved items. Run `/oracle` to resolve them first."

### Step 4 — Load execution state
Read `execution_plan.md` and `tasks.json`. **Do not read `architecture.md` or `CLAUDE.md` at startup.**

Check `.agentflow/state.json`. If present, report resumed state (milestone, complete/in-progress/pending task_ids) and ask "Continue?". Otherwise identify the first incomplete milestone and report it. If invoked as `/orchestrate debug`, reveal task grouping plan and ask "Proceed?" before continuing.

---

## Decomposition (lazy — only when milestone tasks are stubs in `tasks.json`)

1. Read `commands/orchestrator/planning.md`
2. Read the milestone's `Architecture:` anchor from `execution_plan.md`
3. Load **only that anchor section** from `architecture.md` — never the full document
4. Write full task definitions into `tasks.json`; add parallelism rounds to `execution_plan.md`

---

## Round-sizing heuristic

Before each round: `max_tasks = max(1, (orchestrator_threshold_tokens - current_tokens) / 2500)`.
`current_tokens` = sum of all `TOKENS: input=N` values received this session.
Defer tasks beyond `max_tasks` to a sub-round after the next state save.

---

## Rate-pacing protocol

1. **First agent of every session: spawn alone — never parallel on the first spawn.**
2. After each `TOKENS:` report: `pct_cost = tokens / estimated_limit`. Only spawn next if `remaining > 3 × pct_cost`.
3. Ramp: alone → 2 parallel (if data supports) → 4 parallel (only after Round A cost confirmed safe).
4. At session end: ask user to run `/usage` or `/quota`. Write `~/.agentflow/rate_calibration.json`:
   `{timestamp, start_pct, end_pct, session_tokens, estimated_limit}`

---

## Agent spawn

**Pre-spawn checks (run once before the first agent):**
- Branch must be `main` and working tree clean — stop if not
- If no GitHub remote: `gh repo create --source=. --remote=origin --push`
- Write a stub file for every `owns` path across all tasks (interface stubs with `raise NotImplementedError`)
- If `.gitignore` absent: generate an appropriate one for the project's tech stack and write it
- Generate `.idx` for each file in the round's `reads` lists with ≥ 50 lines: write to `~/.agentflow/cache/<sha256(cwd)>/index/<path>.idx`; one symbol per line as `name:start-end`; Python: ast functions, classes, class methods (`ClassName.method:start-end`); Markdown: H2/H3 headers (`## Header:start-end`); skip if `.idx` newer than source

**Build each agent prompt** — read and embed in order:
1. `commands/worker/system.md` — persona and no-re-read rule
2. `commands/worker/context_bundle.md` — bundle format
3. `commands/worker/testing_guide.md` — TDD rules
4. Full task definitions for this group (from `tasks.json`)
5. The milestone's architecture anchor section (already loaded in Decomposition step)
6. Full contents of each file in the group's `reads` list

Close every spawn prompt with:
> "End your final message with `TOKENS: input=N output=N` — nothing after that line."

Spawn one agent per group with `isolation: "worktree"`. Run groups with no cross-dependencies in parallel (subject to rate-pacing). Save `.agentflow/state.json` after each agent completes.

---

## Review

**Pass 1 — Programmatic (bash, no LLM):**
```bash
git diff main...<branch> --name-only > /tmp/rf.txt && git diff main...<branch> > /tmp/rd.txt
grep -n "NotImplementedError" $(cat /tmp/rf.txt) | grep -v "stub\|test"
grep -n "shell=True" $(cat /tmp/rf.txt)
grep -n "except:" $(cat /tmp/rf.txt)
wc -l $(cat /tmp/rf.txt) | awk '$1 > 250 {print}'
grep -nE "(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}" $(cat /tmp/rf.txt)
```
CRITICAL: hardcoded secrets, signal injection. WARNING: bare except, file size > 250 lines.

**Pass 2 — LLM review (fresh haiku agent):**
Read and embed `commands/reviewer/code_review.md`, `commands/reviewer/security_review.md`, `commands/reviewer/test_review.md` into the review agent prompt. Include pre-filter findings, changed files list, and diff (max 300 lines — keep security-relevant sections if truncating).

- `CRITICAL` → rework (one retry; escalate to user on second failure)
- `DRIFT` → surface at human gate; update `architecture.md` before merging if approved

---

## Human gate

```
PR #N ready — [task_ids] ([module])
  ✓ Code  ✓ Security  [⚠ Drift: X if any]
git diff main...<branch>
Worktree: <absolute path>
PR: <URL>
Reply: yes → merge | no [reason] → rework | skip → continue
```
Emit: `HANDOFF RECOMMENDED: PR #N open for [task_ids] — good stopping point before you review`

**Never merge without explicit "yes".**

---

## Merge

1. Replace merged task in `tasks.json` with slim stub: `{"task_id": "T-NNN", "status": "complete"}`
2. Append full definition to `.agentflow/tasks.archive.json`
3. Mark `MERGED` in `execution_plan.md`
4. If milestone complete: mark `COMPLETE`, decompose next milestone lazily, report to user
5. Save `.agentflow/state.json`
6. Emit: `HANDOFF RECOMMENDED: [task_id] merged — state saved, good stopping point before next round`

---

## Verbosity rules

- Status updates: one line only
- Round reports: table format only — no prose between agent spawns
- Do not narrate grouping logic, overlap scores, or round-sizing calculations

---

## Telemetry

After all tasks complete, write silently to `.agentflow/telemetry.jsonl`:
```json
{"event": "session_complete", "timestamp": "ISO8601", "tasks": N, "groups": N}
```
Run silently: `python agentflow.py handoff "orchestrate: [project name]"`
